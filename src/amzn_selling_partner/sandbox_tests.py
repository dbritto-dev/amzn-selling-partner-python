"""Run every operation of the Amazon clients against the examples embedded in
the pinned model files.

Sources of examples, in order: Amazon ``x-amzn-api-sandbox`` static blocks,
Swagger ``x-examples``/``example`` on the success response, and finally a
synthetic example derived from the schema. Each example becomes an
``httpx2.MockTransport`` request/response pair; the operation is called on the
sync and async clients and the decoded result is checked.

The raw model files are read from the git submodule (or
``AMZN_SELLING_PARTNER_MODELS``); the generated resource modules provide the
operations. Usage (CLI)::

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
from .plugins._amazon.sandbox import sandbox_examples
from .plugins._amazon.specs import api_naming, default_spec_dir, spec_files
from .runtime._naming import param_name
from .runtime._op import Op
from .runtime._pagination import AsyncPage, SyncPage
from .runtime._stream import AsyncStream, Stream

log = logging.getLogger("amzn_selling_partner.sandbox_tests")

_METHODS = ("get", "put", "post", "delete", "patch", "head", "options")


@dataclass(slots=True, kw_only=True)
class Case:
    api: str
    version: str
    operation_id: str
    status: int
    kwargs: dict[str, Any]
    response: Any
    has_response: bool
    source: str


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
    ``$ref`` parameters resolved)."""
    out: dict[str, dict[str, Any]] = {}
    for item in _obj(document.get("paths")).values():
        item_obj = _obj(item)
        shared: list[Any] = item_obj["parameters"] if isinstance(item_obj.get("parameters"), list) else []
        for method in _METHODS:
            op = _obj(item_obj.get(method))
            if not op or not isinstance(op.get("operationId"), str):
                continue
            own: list[Any] = op["parameters"] if isinstance(op.get("parameters"), list) else []
            out[str(op["operationId"])] = {**op, "parameters": [resolve(document, _obj(p)) for p in [*shared, *own]]}
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


def cases_for(op: Op, raw_op: Mapping[str, Any], document: Mapping[str, Any], api: str, version: str) -> list[Case]:
    cases: list[Case] = []
    wire_to_py = {p.wire_name: p.py_name for p in op.params}
    for ex in sandbox_examples(raw_op):
        kwargs: dict[str, Any] = {}
        for wire, value in ex.parameters.items():
            py = wire_to_py.get(wire)
            if py is None:
                py = param_name(wire)
                if py not in op.accepted:
                    log.warning("%s.%s.%s: sandbox example uses unknown parameter %r", api, version, op.operation_id, wire)
                    continue
            kwargs[py] = value
        if ex.has_body:
            if op.body is None:
                log.warning("%s.%s.%s: sandbox example carries a body but the operation has none; ignored", api, version, op.operation_id)
            else:
                kwargs["body"] = ex.body
        _fill_required(op, raw_op, document, kwargs)
        cases.append(
            Case(
                api=api,
                version=version,
                operation_id=op.operation_id,
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
        _fill_required(op, raw_op, document, kwargs)
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
                api=api,
                version=version,
                operation_id=op.operation_id,
                status=status,
                kwargs=kwargs,
                response=body,
                has_response=has_response,
                source="synthetic",
            )
        )
        break
    return cases


def _fill_required(op: Op, raw_op: Mapping[str, Any], document: Mapping[str, Any], kwargs: dict[str, Any]) -> None:
    raw_params = {str(_obj(p).get("name")): _obj(p) for p in cast(list[Any], raw_op.get("parameters") or [])}
    py_to_wire = {p.py_name: p.wire_name for p in op.params}
    for name in op.required:
        if name in kwargs:
            continue
        if name == "body":
            body_param = next((p for p in raw_params.values() if p.get("in") == "body"), None)
            schema = (
                _obj(body_param.get("schema"))
                if body_param
                else _obj(_obj(_obj(_obj(raw_op.get("requestBody")).get("content")).get("application/json")).get("schema"))
            )
            kwargs["body"] = example_from_schema(document, schema) if schema else b"example"
        else:
            p = raw_params.get(py_to_wire.get(name, ""))
            if p is None:
                kwargs[name] = "example"
            elif "schema" in p:
                kwargs[name] = example_from_schema(document, _obj(p["schema"]))
            else:
                kwargs[name] = example_from_schema(
                    document, {k: v for k, v in p.items() if k not in ("name", "in", "required", "description")}
                )


def make_transport(case: Case, op: Op) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method != op.method:
            return httpx2.Response(405, json={"errors": [{"code": "MethodNotAllowed", "message": request.method}]})
        if case.has_response and case.response is not None:
            if isinstance(case.response, (str, bytes)):
                return httpx2.Response(case.status, content=case.response if isinstance(case.response, bytes) else case.response.encode())
            return httpx2.Response(case.status, json=case.response)
        return httpx2.Response(case.status)

    return httpx2.MockTransport(handler)


def run_case(client_factory: Callable[[httpx2.MockTransport | None], Any], case: Case, *, mode: str) -> Outcome:
    client = client_factory(None)
    op = getattr(getattr(client, case.api), case.version).operation(case.operation_id)
    transport = make_transport(case, op)
    client = client_factory(transport)
    method = getattr(getattr(getattr(client, case.api), case.version), op.name)

    async def go() -> Any:
        result = method(**case.kwargs)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, (Stream, AsyncStream)):
            await result.aclose() if isinstance(result, AsyncStream) else result.close()
        return result

    try:
        result = asyncio.run(go()) if mode == "async" else method(**case.kwargs)
        if isinstance(result, (Stream, AsyncStream)):
            result.close() if isinstance(result, Stream) else None
    except ValidationError as exc:
        return Outcome(case=case, mode=mode, ok=False, error=f"response does not validate: {exc.errors()[:3]}")
    except (TypeError, ValueError) as exc:
        return Outcome(case=case, mode=mode, ok=False, error=f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001 - reported as a failed case, never swallowed silently
        if case.status >= 400:
            return Outcome(case=case, mode=mode, ok=True, result=exc)
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
    if isinstance(result, (SyncPage, AsyncPage)):
        _ = cast(Any, result).items  # exercise the getters
    return Outcome(case=case, mode=mode, ok=True, result=result)


def run(
    sync_factory: Callable[[httpx2.MockTransport | None], Any],
    async_factory: Callable[[httpx2.MockTransport | None], Any],
    apis: Iterable[str] | None = None,
    *,
    models_dir: pathlib.Path | None = None,
) -> list[Outcome]:
    probe = sync_factory(None)
    names = list(apis) if apis else probe.apis
    documents = load_documents(models_dir)
    outcomes: list[Outcome] = []
    for api_name in names:
        container = probe.api(api_name)
        for version in container.versions:
            document = documents.get((container.api, version))
            if document is None:
                log.warning("%s.%s: no model file found; skipped", container.api, version)
                continue
            raw_ops = raw_operations(document)
            resource = container.version(version)
            for op in resource.operations.values():
                raw_op = raw_ops.get(op.operation_id)
                if raw_op is None:
                    log.warning("%s.%s.%s: not in the model file; skipped", container.api, version, op.operation_id)
                    continue
                for case in cases_for(op, raw_op, document, container.api, version):
                    outcomes.append(run_case(sync_factory, case, mode="sync"))
                    outcomes.append(run_case(async_factory, case, mode="async"))
    return outcomes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run sandbox examples through the Amazon clients.")
    parser.add_argument("apis", nargs="*", help="API names (default: all)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    from .plugins.amazon_spapi import AsyncSellingPartner, SellingPartner

    def sync_factory(transport: httpx2.MockTransport | None) -> Any:
        return SellingPartner(transport=transport, sandbox=True, throttle=False, max_retries=0)

    def async_factory(transport: httpx2.MockTransport | None) -> Any:
        return AsyncSellingPartner(transport=transport, sandbox=True, throttle=False, max_retries=0)

    outcomes = run(sync_factory, async_factory, args.apis or None)
    failed = [o for o in outcomes if not o.ok]
    for o in failed:
        print(f"FAIL {o.mode} {o.case.api}.{o.case.version}.{o.case.operation_id} [{o.case.status}] {o.error}")
    print(f"{len(outcomes) - len(failed)} passed, {len(failed)} failed, {len(outcomes)} total")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
