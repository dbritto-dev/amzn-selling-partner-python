"""OpenAPI 3.0 / 3.1 -> IR normaliser (typed by ``raw.OpenAPIDocument``)."""

from __future__ import annotations

from typing import Any, TypeVar

from ._schema import SchemaConverter
from .ir import Document, Operation, Parameter, RequestBody, Response, Schema, Server, Style
from .raw import OpenAPIDocument, RawHeader, RawMediaType, RawParameter, RawPathItem, RawRequestBody, RawResponse, RawServer
from .refs import RefResolver

M = TypeVar("M", RawParameter, RawRequestBody, RawResponse, RawHeader)

_DEFAULT_STYLE: dict[str, Style] = {"query": "form", "cookie": "form", "path": "simple", "header": "simple"}


def normalize_openapi3(raw: Any, *, source: str, digest: str) -> Document:
    doc = OpenAPIDocument.model_validate(raw)
    resolver = RefResolver(source, raw)
    conv = SchemaConverter(resolver)
    components = doc.components
    conv.register_all((components.schemas or {}) if components else {}, source, "/components/schemas")

    servers = tuple(_server(s) for s in doc.servers or ())

    operations: list[Operation] = []
    for path, item in doc.paths.items():
        if item.ref:
            item = resolver.lookup_model(item.ref, source, RawPathItem)[0]
        path_params = [_deref(p, resolver, source, RawParameter) for p in item.parameters or []]
        for method, op in item.operations():
            op_params = [_deref(p, resolver, source, RawParameter) for p in op.parameters or []]
            merged: dict[tuple[str, str], RawParameter] = {}
            for p in [*path_params, *op_params]:
                merged[(str(p.name), str(p.in_))] = p
            params = tuple(_parameter(p, conv, source) for p in merged.values())

            body: RequestBody | None = None
            if op.request_body is not None:
                rb = _deref(op.request_body, resolver, source, RawRequestBody)
                body = RequestBody(
                    content=_content(rb.content, conv, source),
                    required=bool(rb.required),
                    description=rb.description,
                    extensions=rb.extensions,
                )

            responses: dict[str, Response] = {}
            for code, resp in (op.responses or {}).items():
                resp = _deref(resp, resolver, source, RawResponse)
                headers: dict[str, Schema] = {}
                for hname, h in (resp.headers or {}).items():
                    h = _deref(h, resolver, source, RawHeader)
                    headers[hname] = conv.convert(h.schema_ if h.schema_ is not None else True, source)
                responses[code] = Response(
                    status=code,
                    description=resp.description,
                    content=_content(resp.content, conv, source),
                    headers=headers,
                    extensions=resp.extensions,
                )
            operations.append(
                Operation(
                    operation_id=op.operation_id or f"{method}_{path}",
                    method=method,
                    path=path,
                    summary=op.summary,
                    description=op.description,
                    tags=tuple(op.tags or ()),
                    parameters=params,
                    request_body=body,
                    responses=responses,
                    deprecated=bool(op.deprecated),
                    extensions=op.extensions,
                )
            )

    return Document(
        title=doc.info.title or "",
        version=str(doc.info.version or ""),
        format="openapi3",
        source=source,
        hash=digest,
        description=doc.info.description,
        servers=servers,
        operations=tuple(operations),
        schemas=dict(conv.schemas),
        extensions=doc.extensions,
    )


def _deref(node: M, resolver: RefResolver, source: str, model: type[M]) -> M:
    return resolver.lookup_model(node.ref, source, model)[0] if node.ref else node


def _server(s: RawServer) -> Server:
    variables = {name: str(v.default if v.default is not None else "") for name, v in (s.variables or {}).items()}
    return Server(url=s.url, description=s.description, variables=variables, extensions=s.extensions)


def _content(content: dict[str, RawMediaType] | None, conv: SchemaConverter, source: str) -> dict[str, Schema]:
    return {media: conv.convert(mt.schema_ if mt.schema_ is not None else True, source) for media, mt in (content or {}).items()}


def _parameter(p: RawParameter, conv: SchemaConverter, source: str) -> Parameter:
    loc = str(p.in_)
    if p.schema_ is not None:
        schema = conv.convert(p.schema_, source)
    elif p.content:
        schema = next(iter(_content(p.content, conv, source).values()), Schema())
    else:
        schema = Schema()
    style: Style = p.style or _DEFAULT_STYLE.get(loc, "form")  # type: ignore[assignment]
    explode = p.explode if p.explode is not None else style == "form"
    return Parameter(
        name=str(p.name),
        location=loc,  # type: ignore[arg-type]
        schema=schema,
        required=bool(p.required) or loc == "path",
        description=p.description,
        style=style,
        explode=bool(explode),
        allow_reserved=bool(p.allow_reserved),
        deprecated=bool(p.deprecated),
        extensions=p.extensions,
    )


__all__ = ["normalize_openapi3"]
