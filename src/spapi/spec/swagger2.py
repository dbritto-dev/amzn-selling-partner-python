"""Swagger 2.0 -> IR normaliser."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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


def normalize_swagger2(raw: Mapping[str, Any], *, source: str, digest: str) -> Document:
    resolver = RefResolver(source, raw)
    conv = SchemaConverter(resolver)
    conv.register_all(raw.get("definitions"), source, "/definitions")

    info = raw.get("info") or {}
    schemes = raw.get("schemes") or ["https"]
    host = raw.get("host")
    base_path = (raw.get("basePath") or "").rstrip("/")
    servers: tuple[Server, ...] = ()
    if host:
        servers = tuple(Server(url=f"{scheme}://{host}{base_path}") for scheme in schemes)
    elif base_path:
        servers = (Server(url=base_path),)

    root_consumes = list(raw.get("consumes") or ["application/json"])
    root_produces = list(raw.get("produces") or ["application/json"])

    operations: list[Operation] = []
    for path, item in (raw.get("paths") or {}).items():
        if not isinstance(item, Mapping):
            continue
        if "$ref" in item:
            item = resolver.lookup(item["$ref"], source)[0]
        path_params = [_deref_param(p, resolver, source) for p in item.get("parameters") or []]
        for method in _METHODS:
            op = item.get(method)
            if not isinstance(op, Mapping):
                continue
            op_params = [_deref_param(p, resolver, source) for p in op.get("parameters") or []]
            merged: dict[tuple[str, str], Mapping[str, Any]] = {}
            for p in [*path_params, *op_params]:
                merged[(str(p.get("name")), str(p.get("in")))] = p
            consumes = list(op.get("consumes") or root_consumes)
            produces = list(op.get("produces") or root_produces)
            params: list[Parameter] = []
            body: RequestBody | None = None
            form_props: dict[str, Schema] = {}
            form_required: set[str] = set()
            form_has_file = False
            for p in merged.values():
                loc = p.get("in")
                if loc == "body":
                    schema = conv.convert(p.get("schema") or {}, source)
                    body = RequestBody(
                        content={media: schema for media in consumes},
                        required=bool(p.get("required")),
                        description=p.get("description"),
                        extensions=extensions_of(p),
                    )
                elif loc == "formData":
                    form_props[str(p["name"])] = _param_schema(p, conv, source)
                    if p.get("required"):
                        form_required.add(str(p["name"]))
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
            for code, resp in (op.get("responses") or {}).items():
                if not isinstance(resp, Mapping):
                    continue
                if "$ref" in resp:
                    resp = resolver.lookup(resp["$ref"], source)[0]
                content: dict[str, Schema] = {}
                if isinstance(resp.get("schema"), Mapping):
                    schema = conv.convert(resp["schema"], source)
                    content = {media: schema for media in produces}
                headers = {
                    hname: _param_schema(h, conv, source)
                    for hname, h in (resp.get("headers") or {}).items()
                    if isinstance(h, Mapping)
                }
                responses[str(code)] = Response(
                    status=str(code),
                    description=resp.get("description"),
                    content=content,
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
                    parameters=tuple(params),
                    request_body=body,
                    responses=responses,
                    deprecated=bool(op.get("deprecated")),
                    extensions=extensions_of(op),
                )
            )

    return Document(
        title=str(info.get("title") or ""),
        version=str(info.get("version") or ""),
        format="swagger2",
        source=source,
        hash=digest,
        description=info.get("description"),
        servers=servers,
        operations=tuple(operations),
        schemas=dict(conv.schemas),
        extensions=extensions_of(raw),
    )


def _deref_param(p: Any, resolver: RefResolver, source: str) -> Mapping[str, Any]:
    if isinstance(p, Mapping) and "$ref" in p:
        return resolver.lookup(p["$ref"], source)[0]
    return p


def _param_schema(p: Mapping[str, Any], conv: SchemaConverter, source: str) -> Schema:
    node = {k: v for k, v in p.items() if k in _PARAM_SCHEMA_KEYS}
    if "description" in p:
        node["description"] = p["description"]
    return conv.convert(node, source)


def _parameter(p: Mapping[str, Any], conv: SchemaConverter, source: str) -> Parameter:
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
        description=p.get("description"),
        style=style,
        explode=explode,
        allow_reserved=bool(p.get("allowReserved")),
        extensions=extensions_of(p),
    )


__all__ = ["normalize_swagger2"]
