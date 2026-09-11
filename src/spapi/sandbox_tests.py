"""Run every operation of a client against its embedded examples.

Sources of examples, in order: ``annotations["sandbox_examples"]`` (Amazon
``x-amzn-api-sandbox`` static blocks, normalised by the plugin), OpenAPI
``examples``/``example`` on the success response, and finally a synthetic
example derived from the schema. Each example becomes an
``httpx2.MockTransport`` request/response pair; the operation is called on the
sync and async clients and the decoded result is checked.

Usage (CLI)::

    python -m spapi.sandbox_tests orders listings_items   # or no args = all APIs
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import logging
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import httpx2
from pydantic import ValidationError

from ._examples import example_from_schema
from .compile.naming import param_name
from .compile.operations import CompiledOp
from .runtime._pagination import AsyncPage, SyncPage
from .runtime._stream import AsyncStream, Stream
from .spec.ir import Document

log = logging.getLogger("spapi.sandbox_tests")


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


def cases_for(op: CompiledOp, document: Document, api: str, version: str) -> list[Case]:
    cases: list[Case] = []
    wire_to_py = {p.wire_name: p.py_name for p in [*op.path_params, *op.query_params, *op.header_params]}
    for ex in op.annotations.get("sandbox_examples", ()):
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
        _fill_required(op, document, kwargs)
        cases.append(Case(api=api, version=version, operation_id=op.operation_id, status=ex.status, kwargs=kwargs, response=ex.response, has_response=ex.has_response, source=ex.source))
    if cases:
        return cases
    # OpenAPI examples / synthetic
    for code, resp in op.ir.responses.items():
        if not code.startswith("2"):
            continue
        status = int(code.replace("X", "0"))
        kwargs = {}
        _fill_required(op, document, kwargs)
        body: Any = None
        has_response = False
        js = resp.json_schema
        examples = resp.extensions.get("x-examples") or {}
        if isinstance(examples, dict) and examples:
            body, has_response = next(iter(examples.values())), True
        elif js is not None:
            resolved = document.resolve(js)
            if resolved.example is not None:
                body, has_response = resolved.example, True
            else:
                body, has_response = example_from_schema(document, js, all_fields=True), True
        cases.append(Case(api=api, version=version, operation_id=op.operation_id, status=status, kwargs=kwargs, response=body, has_response=has_response, source="synthetic"))
        break
    return cases


def _fill_required(op: CompiledOp, document: Document, kwargs: dict[str, Any]) -> None:
    ir_params = {param_name(p.name): p for p in op.ir.parameters}
    for name in op.required:
        if name in kwargs:
            continue
        if name == "body":
            rb = op.ir.request_body
            if rb is not None and rb.json_schema is not None:
                kwargs["body"] = example_from_schema(document, rb.json_schema)
            else:
                kwargs["body"] = b"example"
        else:
            p = ir_params.get(name)
            kwargs[name] = example_from_schema(document, p.schema) if p is not None else "example"


def make_transport(case: Case, op: CompiledOp) -> httpx2.MockTransport:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method != op.method:
            return httpx2.Response(405, json={"errors": [{"code": "MethodNotAllowed", "message": request.method}]})
        if case.has_response and case.response is not None:
            if isinstance(case.response, (dict, list)):
                return httpx2.Response(case.status, json=case.response)
            return httpx2.Response(case.status, content=str(case.response).encode())
        return httpx2.Response(case.status)

    return httpx2.MockTransport(handler)


def run_case(client_factory: Callable[[httpx2.MockTransport], Any], case: Case, *, mode: str) -> Outcome:
    client = client_factory(None)  # type: ignore[arg-type]
    api = getattr(client, case.api)
    version = getattr(api, case.version)
    op = version.operation(case.operation_id)
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
        result.items  # noqa: B018 - exercise the getters
    return Outcome(case=case, mode=mode, ok=True, result=result)


def run(
    sync_factory: Callable[[httpx2.MockTransport], Any],
    async_factory: Callable[[httpx2.MockTransport], Any],
    apis: Iterable[str] | None = None,
) -> list[Outcome]:
    probe = sync_factory(None)  # type: ignore[arg-type]
    names = list(apis) if apis else probe.apis
    outcomes: list[Outcome] = []
    for api_name in names:
        container = probe.api(api_name)
        for version in container.versions:
            av = container.version(version)
            for op in av.operations:
                for case in cases_for(op, av.document, api_name, version):
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
