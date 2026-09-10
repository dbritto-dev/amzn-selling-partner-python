"""OpenAPI 3.0 / 3.1 -> IR normaliser."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._schema import SchemaConverter, extensions_of
from .ir import Document, Operation, Parameter, RequestBody, Response, Schema, Server, Style
from .refs import RefResolver

_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

_DEFAULT_STYLE: dict[str, Style] = {
    "query": "form",
    "cookie": "form",
    "path": "simple",
    "header": "simple",
}


def normalize_openapi3(raw: Mapping[str, Any], *, source: str, digest: str) -> Document:
    resolver = RefResolver(source, raw)
    conv = SchemaConverter(resolver)
    components = raw.get("components") or {}
    conv.register_all(components.get("schemas"), source, "/components/schemas")

    info = raw.get("info") or {}
    servers = tuple(_server(s) for s in raw.get("servers") or () if isinstance(s, Mapping))

    operations: list[Operation] = []
    for path, item in (raw.get("paths") or {}).items():
        if not isinstance(item, Mapping):
            continue
        if "$ref" in item:
            item = resolver.lookup(item["$ref"], source)[0]
        path_params = [_deref(p, resolver, source) for p in item.get("parameters") or []]
        for method in _METHODS:
            op = item.get(method)
            if not isinstance(op, Mapping):
                continue
            op_params = [_deref(p, resolver, source) for p in op.get("parameters") or []]
            merged: dict[tuple[str, str], Mapping[str, Any]] = {}
            for p in [*path_params, *op_params]:
                merged[(str(p.get("name")), str(p.get("in")))] = p
            params = tuple(_parameter(p, conv, source, resolver) for p in merged.values())

            body: RequestBody | None = None
            rb = op.get("requestBody")
            if isinstance(rb, Mapping):
                rb = _deref(rb, resolver, source)
                body = RequestBody(
                    content=_content(rb.get("content"), conv, source),
                    required=bool(rb.get("required")),
                    description=rb.get("description"),
                    extensions=extensions_of(rb),
                )

            responses: dict[str, Response] = {}
            for code, resp in (op.get("responses") or {}).items():
                if not isinstance(resp, Mapping):
                    continue
                resp = _deref(resp, resolver, source)
                headers: dict[str, Schema] = {}
                for hname, h in (resp.get("headers") or {}).items():
                    if isinstance(h, Mapping):
                        h = _deref(h, resolver, source)
                        headers[hname] = conv.convert(h.get("schema") or {}, source)
                responses[str(code)] = Response(
                    status=str(code),
                    description=resp.get("description"),
                    content=_content(resp.get("content"), conv, source),
                    headers=headers,
                    extensions=extensions_of(resp),
                )
            operation_id = op.get("operationId") or f"{method}_{path}"
            operations.append(
                Operation(
                    operation_id=str(operation_id),
                    method=method,
                    path=str(path),
                    summary=op.get("summary"),
                    description=op.get("description"),
                    tags=tuple(str(t) for t in op.get("tags") or ()),
                    parameters=params,
                    request_body=body,
                    responses=responses,
                    deprecated=bool(op.get("deprecated")),
                    extensions=extensions_of(op),
                )
            )

    return Document(
        title=str(info.get("title") or ""),
        version=str(info.get("version") or ""),
        format="openapi3",
        source=source,
        hash=digest,
        description=info.get("description"),
        servers=servers,
        operations=tuple(operations),
        schemas=dict(conv.schemas),
        extensions=extensions_of(raw),
    )


def _deref(node: Any, resolver: RefResolver, source: str) -> Mapping[str, Any]:
    if isinstance(node, Mapping) and "$ref" in node:
        return resolver.lookup(node["$ref"], source)[0]
    return node


def _server(s: Mapping[str, Any]) -> Server:
    variables = {
        name: str((v or {}).get("default", ""))
        for name, v in (s.get("variables") or {}).items()
        if isinstance(v, Mapping)
    }
    return Server(
        url=str(s.get("url", "")),
        description=s.get("description"),
        variables=variables,
        extensions=extensions_of(s),
    )


def _content(content: Any, conv: SchemaConverter, source: str) -> dict[str, Schema]:
    out: dict[str, Schema] = {}
    if isinstance(content, Mapping):
        for media, mt in content.items():
            if isinstance(mt, Mapping):
                out[str(media)] = conv.convert(mt.get("schema") or {}, source)
    return out


def _parameter(p: Mapping[str, Any], conv: SchemaConverter, source: str, resolver: RefResolver) -> Parameter:
    loc = str(p.get("in"))
    if isinstance(p.get("schema"), (Mapping, bool)):
        schema = conv.convert(p["schema"], source)
    elif isinstance(p.get("content"), Mapping):
        schema = next(iter(_content(p["content"], conv, source).values()), Schema())
    else:
        schema = Schema()
    style: Style = p.get("style") or _DEFAULT_STYLE.get(loc, "form")  # type: ignore[assignment]
    explode = p.get("explode")
    if explode is None:
        explode = style == "form"
    return Parameter(
        name=str(p["name"]),
        location=loc,  # type: ignore[arg-type]
        schema=schema,
        required=bool(p.get("required")) or loc == "path",
        description=p.get("description"),
        style=style,
        explode=bool(explode),
        allow_reserved=bool(p.get("allowReserved")),
        deprecated=bool(p.get("deprecated")),
        extensions=extensions_of(p),
    )


__all__ = ["normalize_openapi3"]
