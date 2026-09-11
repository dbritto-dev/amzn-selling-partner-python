"""OpenAPI 3.0 / 3.1 -> IR normaliser."""

from __future__ import annotations

from typing import Any

from ._jsonutil import JsonObject, as_list, as_object, obj, objects, strings, text
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


def normalize_openapi3(raw: JsonObject, *, source: str, digest: str) -> Document:
    resolver = RefResolver(source, raw)
    conv = SchemaConverter(resolver)
    components = obj(raw, "components")
    conv.register_all(obj(components, "schemas"), source, "/components/schemas")

    info = obj(raw, "info")
    servers = tuple(_server(server) for raw_server in as_list(raw.get("servers")) if (server := as_object(raw_server)) is not None)

    operations: list[Operation] = []
    for path, item in objects(raw, "paths"):
        if "$ref" in item:
            item = resolver.lookup_object(str(item["$ref"]), source)[0]
        path_params = [_deref(p, resolver, source) for p in as_list(item.get("parameters"))]
        for method in _METHODS:
            op = as_object(item.get(method))
            if op is None:
                continue
            op_params = [_deref(p, resolver, source) for p in as_list(op.get("parameters"))]
            merged: dict[tuple[str, str], JsonObject] = {}
            for p in [*path_params, *op_params]:
                if p is not None:
                    merged[(str(p.get("name")), str(p.get("in")))] = p
            params = tuple(_parameter(p, conv, source) for p in merged.values())

            body: RequestBody | None = None
            rb = _deref(op.get("requestBody"), resolver, source)
            if rb is not None:
                body = RequestBody(
                    content=_content(rb.get("content"), conv, source),
                    required=bool(rb.get("required")),
                    description=text(rb, "description"),
                    extensions=extensions_of(rb),
                )

            responses: dict[str, Response] = {}
            for code, resp in objects(op, "responses"):
                resp = _deref(resp, resolver, source) or resp
                headers: dict[str, Schema] = {}
                for hname, h in objects(resp, "headers"):
                    h = _deref(h, resolver, source) or h
                    headers[hname] = conv.convert(obj(h, "schema"), source)
                responses[code] = Response(
                    status=code,
                    description=text(resp, "description"),
                    content=_content(resp.get("content"), conv, source),
                    headers=headers,
                    extensions=extensions_of(resp),
                )
            operation_id = text(op, "operationId") or f"{method}_{path}"
            operations.append(
                Operation(
                    operation_id=operation_id,
                    method=method,
                    path=path,
                    summary=text(op, "summary"),
                    description=text(op, "description"),
                    tags=strings(op, "tags"),
                    parameters=params,
                    request_body=body,
                    responses=responses,
                    deprecated=bool(op.get("deprecated")),
                    extensions=extensions_of(op),
                )
            )

    return Document(
        title=text(info, "title") or "",
        version=str(info.get("version") or ""),
        format="openapi3",
        source=source,
        hash=digest,
        description=text(info, "description"),
        servers=servers,
        operations=tuple(operations),
        schemas=dict(conv.schemas),
        extensions=extensions_of(raw),
    )


def _deref(node: Any, resolver: RefResolver, source: str) -> JsonObject | None:
    o = as_object(node)
    if o is not None and "$ref" in o:
        return resolver.lookup_object(str(o["$ref"]), source)[0]
    return o


def _server(s: JsonObject) -> Server:
    variables = {name: str(v.get("default", "")) for name, v in objects(s, "variables")}
    return Server(url=text(s, "url") or "", description=text(s, "description"), variables=variables, extensions=extensions_of(s))


def _content(content: Any, conv: SchemaConverter, source: str) -> dict[str, Schema]:
    out: dict[str, Schema] = {}
    node = as_object(content)
    if node is not None:
        for media, mt_raw in node.items():
            mt = as_object(mt_raw)
            if mt is not None:
                out[str(media)] = conv.convert(obj(mt, "schema"), source)
    return out


def _parameter(p: JsonObject, conv: SchemaConverter, source: str) -> Parameter:
    loc = str(p.get("in"))
    raw_schema = p.get("schema")
    if isinstance(raw_schema, bool):
        schema = conv.convert(raw_schema, source)
    elif (schema_obj := as_object(raw_schema)) is not None:
        schema = conv.convert(schema_obj, source)
    elif as_object(p.get("content")) is not None:
        schema = next(iter(_content(p["content"], conv, source).values()), Schema())
    else:
        schema = Schema()
    style: Style = text(p, "style") or _DEFAULT_STYLE.get(loc, "form")  # type: ignore[assignment]
    explode = p.get("explode")
    if explode is None:
        explode = style == "form"
    return Parameter(
        name=str(p["name"]),
        location=loc,  # type: ignore[arg-type]
        schema=schema,
        required=bool(p.get("required")) or loc == "path",
        description=text(p, "description"),
        style=style,
        explode=bool(explode),
        allow_reserved=bool(p.get("allowReserved")),
        deprecated=bool(p.get("deprecated")),
        extensions=extensions_of(p),
    )


__all__ = ["normalize_openapi3"]
