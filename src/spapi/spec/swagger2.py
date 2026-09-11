"""Swagger 2.0 -> IR normaliser."""

from __future__ import annotations

from typing import Any

from ._jsonutil import JsonObject, as_list, as_object, obj, objects, strings, text
from ._schema import SchemaConverter, extensions_of
from .ir import Document, Operation, Parameter, RequestBody, Response, Schema, Server, Style
from .refs import RefResolver

_METHODS = ("get", "put", "post", "delete", "options", "head", "patch")

# collectionFormat -> (style, explode)
_COLLECTION_FORMATS: dict[str, tuple[Style, bool]] = {
    "csv": ("form", False),
    "ssv": ("spaceDelimited", False),
    "tsv": ("tabDelimited", False),
    "pipes": ("pipeDelimited", False),
    "multi": ("form", True),
}

_PARAM_SCHEMA_KEYS = (
    "type",
    "format",
    "items",
    "enum",
    "default",
    "minimum",
    "maximum",
    "pattern",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "uniqueItems",
    "multipleOf",
    "x-nullable",
)


def normalize_swagger2(raw: JsonObject, *, source: str, digest: str) -> Document:
    resolver = RefResolver(source, raw)
    conv = SchemaConverter(resolver)
    conv.register_all(obj(raw, "definitions"), source, "/definitions")

    info = obj(raw, "info")
    schemes = list(strings(raw, "schemes")) or ["https"]
    host = text(raw, "host")
    base_path = (text(raw, "basePath") or "").rstrip("/")
    servers: tuple[Server, ...] = ()
    if host:
        servers = tuple(Server(url=f"{scheme}://{host}{base_path}") for scheme in schemes)
    elif base_path:
        servers = (Server(url=base_path),)

    root_consumes = list(strings(raw, "consumes")) or ["application/json"]
    root_produces = list(strings(raw, "produces")) or ["application/json"]

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
            consumes = list(strings(op, "consumes")) or root_consumes
            produces = list(strings(op, "produces")) or root_produces
            params: list[Parameter] = []
            body: RequestBody | None = None
            form_props: dict[str, Schema] = {}
            form_required: set[str] = set()
            form_has_file = False
            for p in merged.values():
                loc = p.get("in")
                if loc == "body":
                    schema = conv.convert(obj(p, "schema"), source)
                    body = RequestBody(
                        content={media: schema for media in consumes},
                        required=bool(p.get("required")),
                        description=text(p, "description"),
                        extensions=extensions_of(p),
                    )
                elif loc == "formData":
                    name = str(p["name"])
                    form_props[name] = _param_schema(p, conv, source)
                    if p.get("required"):
                        form_required.add(name)
                    form_has_file = form_has_file or p.get("type") == "file"
                else:
                    params.append(_parameter(p, conv, source))
            if form_props:
                media = "multipart/form-data" if form_has_file else "application/x-www-form-urlencoded"
                for m in consumes:
                    if m in ("multipart/form-data", "application/x-www-form-urlencoded"):
                        media = m
                body = RequestBody(
                    content={media: Schema(type="object", properties=form_props, required=frozenset(form_required))},
                    required=bool(form_required),
                )
            responses: dict[str, Response] = {}
            for code, resp in objects(op, "responses"):
                if "$ref" in resp:
                    resp = resolver.lookup_object(str(resp["$ref"]), source)[0]
                content: dict[str, Schema] = {}
                resp_schema = as_object(resp.get("schema"))
                if resp_schema is not None:
                    schema = conv.convert(resp_schema, source)
                    content = {media: schema for media in produces}
                headers = {hname: _param_schema(h, conv, source) for hname, h in objects(resp, "headers")}
                responses[code] = Response(
                    status=code,
                    description=text(resp, "description"),
                    content=content,
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
                    parameters=tuple(params),
                    request_body=body,
                    responses=responses,
                    deprecated=bool(op.get("deprecated")),
                    extensions=extensions_of(op),
                )
            )

    return Document(
        title=text(info, "title") or "",
        version=str(info.get("version") or ""),
        format="swagger2",
        source=source,
        hash=digest,
        description=text(info, "description"),
        servers=servers,
        operations=tuple(operations),
        schemas=dict(conv.schemas),
        extensions=extensions_of(raw),
    )


def _deref(p: Any, resolver: RefResolver, source: str) -> JsonObject | None:
    node = as_object(p)
    if node is not None and "$ref" in node:
        return resolver.lookup_object(str(node["$ref"]), source)[0]
    return node


def _param_schema(p: JsonObject, conv: SchemaConverter, source: str) -> Schema:
    node: dict[str, Any] = {k: v for k, v in p.items() if k in _PARAM_SCHEMA_KEYS}
    if "description" in p:
        node["description"] = p["description"]
    return conv.convert(node, source)


def _parameter(p: JsonObject, conv: SchemaConverter, source: str) -> Parameter:
    loc = str(p.get("in"))
    style, explode = _COLLECTION_FORMATS.get(str(p.get("collectionFormat") or "csv"), ("form", False))
    if loc in ("path", "header"):
        style = "simple"
        explode = False
    elif p.get("type") != "array":
        style, explode = "form", True
    return Parameter(
        name=str(p["name"]),
        location=loc,  # type: ignore[arg-type]
        schema=_param_schema(p, conv, source),
        required=bool(p.get("required")) or loc == "path",
        description=text(p, "description"),
        style=style,
        explode=explode,
        allow_reserved=bool(p.get("allowReserved")),
        extensions=extensions_of(p),
    )


__all__ = ["normalize_swagger2"]
