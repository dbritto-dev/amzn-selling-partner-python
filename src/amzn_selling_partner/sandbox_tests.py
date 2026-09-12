"""Run every operation of the Amazon clients against the examples embedded in
the pinned model files.

Sources of examples, in order: Amazon ``x-amzn-api-sandbox`` static blocks,
Swagger ``x-examples``/``example`` on the success response, and finally a
synthetic example derived from the schema. Each example becomes an
``httpx2.MockTransport`` request/response pair; the generated method is called
on the sync and async clients and the decoded result is checked.

The raw model files are read from the git submodule (or
``AMZN_SELLING_PARTNER_MODELS``); the generated resources registry
(``sdk.resources.OPERATIONS``) maps Amazon's operationIds to the methods.
Usage (CLI)::

    python -m amzn_selling_partner.sandbox_tests orders listings_items   # or no args = all APIs
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import logging
import pathlib
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, cast

import httpx2
from pydantic import ValidationError

from ._examples import example_from_schema, resolve
from ._naming import api_version_of, param_name
from .plugins._amazon.sandbox import sandbox_examples
from .plugins._amazon.specs import api_naming, default_spec_dir, spec_files
from .sdk.errors import APIStatusError
from .sdk.resources import OPERATIONS

log = logging.getLogger("amzn_selling_partner.sandbox_tests")

_METHODS = ("get", "put", "post", "delete", "patch", "head", "options")


@dataclass(slots=True, kw_only=True)
class Case:
    module: str
    operation_id: str
    method: str
    status: int
    kwargs: dict[str, Any]
    response: Any
    has_response: bool
    source: str

    @property
    def api(self) -> str:
        av = api_version_of(self.module)
        return av[0] if av else self.module

    @property
    def version(self) -> str:
        av = api_version_of(self.module)
        return av[1] if av else ""


@dataclass(slots=True, kw_only=True)
class Outcome:
    case: Case
    mode: str
    ok: bool
    error: str | None = None
    result: Any = field(default=None, repr=False)


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, Mapping) else {}


def raw_operations(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """``operationId -> raw operation object`` (path-level parameters merged in,
    ``$ref`` parameters resolved). Duplicate operationIds keep the first method."""
    out: dict[str, dict[str, Any]] = {}
    for item in _obj(document.get("paths")).values():
        item_obj = _obj(item)
        shared: list[Any] = item_obj["parameters"] if isinstance(item_obj.get("parameters"), list) else []
        for method in _METHODS:
            op = _obj(item_obj.get(method))
            if not op or not isinstance(op.get("operationId"), str):
                continue
            own: list[Any] = op["parameters"] if isinstance(op.get("parameters"), list) else []
            out.setdefault(str(op["operationId"]), {**op, "parameters": [resolve(document, _obj(p)) for p in [*shared, *own]]})
    return out


def load_documents(root: pathlib.Path | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """``(api, version) -> raw document`` for every pinned model file."""
    docs: dict[tuple[str, str], dict[str, Any]] = {}
    for path in spec_files(root or default_spec_dir()):
        named = api_naming(path)
        if named is None:
            continue
        docs[named] = json.loads(path.read_text())
    return docs


def _signature(fn: Callable[..., Any]) -> tuple[set[str], list[str]]:
    """Accepted keyword arguments and the required ones of a generated method."""
    params = inspect.signature(fn).parameters
    accepted = {n for n in params if n not in ("self", "request_options")}
    required = [n for n, p in params.items() if n in accepted and p.default is inspect.Parameter.empty]
    return accepted, required


def cases_for(
    fn: Callable[..., Any], raw_op: Mapping[str, Any], document: Mapping[str, Any], module: str, operation_id: str, method: str
) -> list[Case]:
    accepted, required = _signature(fn)
    cases: list[Case] = []
    for ex in sandbox_examples(raw_op):
        kwargs: dict[str, Any] = {}
        for wire, value in ex.parameters.items():
            py = param_name(wire)
            if py not in accepted:
                log.warning("%s.%s: sandbox example uses unknown parameter %r", module, operation_id, wire)
                continue
            kwargs[py] = value
        if ex.has_body:
            if "body" not in accepted:
                log.warning("%s.%s: sandbox example carries a body but the operation has none; ignored", module, operation_id)
            else:
                kwargs["body"] = ex.body
        _fill_required(required, raw_op, document, kwargs)
        cases.append(
            Case(
                module=module,
                operation_id=operation_id,
                method=method,
                status=ex.status,
                kwargs=kwargs,
                response=ex.response,
                has_response=ex.has_response,
                source=ex.source,
            )
        )
    if cases:
        return cases
    # Swagger examples / synthetic
    for code, resp in _obj(raw_op.get("responses")).items():
        if not code.startswith("2"):
            continue
        status = int(code.replace("X", "0"))
        kwargs = {}
        _fill_required(required, raw_op, document, kwargs)
        resp_obj = _obj(resp)
        body: Any = None
        has_response = False
        schema = _obj(resp_obj.get("schema")) or _obj(_obj(_obj(_obj(resp_obj.get("content")).get("application/json")).get("schema")))
        examples = _obj(resp_obj.get("x-examples")) or _obj(resp_obj.get("examples"))
        if examples:
            body, has_response = next(iter(examples.values())), True
        elif schema:
            resolved = resolve(document, schema)
            if resolved.get("example") is not None:
                body, has_response = resolved["example"], True
            else:
                body, has_response = example_from_schema(document, schema, all_fields=True), True
        cases.append(
            Case(
                module=module,
                operation_id=operation_id,
                method=method,
                status=status,
                kwargs=kwargs,
                response=body,
                has_response=has_response,
                source="synthetic",
            )
        )
        break
    return cases


def _fill_required(required: list[str], raw_op: Mapping[str, Any], document: Mapping[str, Any], kwargs: dict[str, Any]) -> None:
    raw_params = {
        param_name(str(_obj(p).get("name"))): _obj(p)
        for p in cast(list[Any], raw_op.get("parameters") or [])
        if _obj(p).get("in") != "body"
    }
    for name in required:
        if name in kwargs:
            continue
        if name == "body":
            body_param = next((_obj(p) for p in cast(list[Any], raw_op.get("parameters") or []) if _obj(p).get("in") == "body"), None)
            content = _obj(_obj(raw_op.get("requestBody")).get("content"))
            media = [str(m) for m in cast(list[Any], raw_op.get("consumes") or []) or list(content)]
            schema = _obj(body_param.get("schema")) if body_param else _obj(_obj(content.get("application/json")).get("schema"))
            if schema:
                kwargs["body"] = example_from_schema(document, schema)
            elif any(m.startswith("multipart/") for m in media):
                kwargs["body"] = {"file": ("example.bin", b"example")}
            elif any(m == "application/x-www-form-urlencoded" for m in media):
                kwargs["body"] = {"field": "example"}
            elif any(m.startswith("text/") for m in media):
                kwargs["body"] = "example"
            else:
                kwargs["body"] = b"example"
        else:
            p = raw_params.get(name)
            if p is None:
                kwargs[name] = "example"
            elif "schema" in p:
                kwargs[name] = example_from_schema(document, _obj(p["schema"]))
            else:
                kwargs[name] = example_from_schema(
                    document, {k: v for k, v in p.items() if k not in ("name", "in", "required", "description")}
                )


def make_transport(case: Case, http_method: str) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method != http_method:
            return httpx2.Response(405, json={"errors": [{"code": "MethodNotAllowed", "message": request.method}]})
        if case.has_response and case.response is not None:
            if isinstance(case.response, (str, bytes)):
                return httpx2.Response(case.status, content=case.response if isinstance(case.response, bytes) else case.response.encode())
            return httpx2.Response(case.status, json=case.response)
        return httpx2.Response(case.status)

    return httpx2.MockTransport(handler)


def run_case(client_factory: Callable[[httpx2.MockTransport | None], Any], case: Case, http_method: str, *, mode: str) -> Outcome:
    client = client_factory(make_transport(case, http_method))
    method = getattr(getattr(client, case.module), case.method)

    async def go() -> Any:
        result = method(**case.kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result

    try:
        result = asyncio.run(go()) if mode == "async" else method(**case.kwargs)
    except ValidationError as exc:
        return Outcome(case=case, mode=mode, ok=False, error=f"response does not validate: {exc.errors()[:3]}")
    except (TypeError, ValueError) as exc:
        return Outcome(case=case, mode=mode, ok=False, error=f"{type(exc).__name__}: {exc}")
    except APIStatusError as exc:
        if case.status >= 400:
            return Outcome(case=case, mode=mode, ok=True, result=exc)
        return Outcome(case=case, mode=mode, ok=False, error=f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001 - reported as a failed case, never swallowed silently
        return Outcome(case=case, mode=mode, ok=False, error=f"{type(exc).__name__}: {exc}")
    finally:
        try:
            if mode == "async":
                asyncio.run(client.aclose())
            else:
                client.close()
        except RuntimeError:
            pass
    if case.status >= 400:
        return Outcome(case=case, mode=mode, ok=False, error="expected an error response")
    return Outcome(case=case, mode=mode, ok=True, result=result)


def run(
    sync_factory: Callable[[httpx2.MockTransport | None], Any],
    async_factory: Callable[[httpx2.MockTransport | None], Any],
    apis: Iterable[str] | None = None,
    *,
    models_dir: pathlib.Path | None = None,
) -> list[Outcome]:
    wanted = set(apis) if apis else None
    documents = load_documents(models_dir)
    raw_cache: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    probe = sync_factory(None)
    outcomes: list[Outcome] = []
    for key, (method, http_method, _path, _paginated, _limit) in OPERATIONS.items():
        module, _, operation_id = key.partition(".")
        operation_id = operation_id.split(":")[0]
        av = api_version_of(module)
        if av is None or (wanted is not None and av[0] not in wanted):
            continue
        document = documents.get(av)
        if document is None:
            log.warning("%s: no model file found; skipped", module)
            continue
        if av not in raw_cache:
            raw_cache[av] = raw_operations(document)
        raw_op = raw_cache[av].get(operation_id)
        if raw_op is None:
            log.warning("%s.%s: not in the model file; skipped", module, operation_id)
            continue
        fn = getattr(getattr(probe, module), method)
        for case in cases_for(fn, raw_op, document, module, operation_id, method):
            outcomes.append(run_case(sync_factory, case, http_method, mode="sync"))
            outcomes.append(run_case(async_factory, case, http_method, mode="async"))
    return outcomes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run sandbox examples through the Amazon clients.")
    parser.add_argument("apis", nargs="*", help="API names (default: all)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    from .plugins.amazon_spapi import AsyncSellingPartner, SellingPartner

    def sync_factory(transport: httpx2.MockTransport | None) -> Any:
        return SellingPartner(transport=transport, sandbox=True, throttle=False, max_retries=0, credentials=None)

    def async_factory(transport: httpx2.MockTransport | None) -> Any:
        return AsyncSellingPartner(transport=transport, sandbox=True, throttle=False, max_retries=0, credentials=None)

    outcomes = run(sync_factory, async_factory, args.apis or None)
    failed = [o for o in outcomes if not o.ok]
    for o in failed:
        print(f"FAIL {o.mode} {o.case.module}.{o.case.operation_id} [{o.case.status}] {o.error}")
    print(f"{len(outcomes) - len(failed)} passed, {len(failed)} failed, {len(outcomes)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
