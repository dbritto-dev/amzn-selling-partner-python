"""Swagger 2.0 -> IR normaliser (typed by ``raw.SwaggerDocument``)."""

from __future__ import annotations

from typing import Any

from ._schema import SchemaConverter
from .ir import Document, Operation, Parameter, RequestBody, Response, Schema, Server, Style
from .raw import RawHeader, RawParameter, RawPathItem, RawResponse, SwaggerDocument
from .refs import RefResolver

# collectionFormat -> (style, explode)
_COLLECTION_FORMATS: dict[str, tuple[Style, bool]] = {
    "csv": ("form", False),
    "ssv": ("spaceDelimited", False),
    "tsv": ("tabDelimited", False),
    "pipes": ("pipeDelimited", False),
    "multi": ("form", True),
}


def normalize_swagger2(raw: Any, *, source: str, digest: str) -> Document:
    doc = SwaggerDocument.model_validate(raw)
    resolver = RefResolver(source, raw)
    conv = SchemaConverter(resolver)
    conv.register_all(doc.definitions or {}, source, "/definitions")

    schemes = doc.schemes or ["https"]
    base_path = (doc.base_path or "").rstrip("/")
    servers: tuple[Server, ...] = ()
    if doc.host:
        servers = tuple(Server(url=f"{scheme}://{doc.host}{base_path}") for scheme in schemes)
    elif base_path:
        servers = (Server(url=base_path),)

    root_consumes = doc.consumes or ["application/json"]
    root_produces = doc.produces or ["application/json"]

    operations: list[Operation] = []
    for path, item in doc.paths.items():
        if item.ref:
            item = resolver.lookup_model(item.ref, source, RawPathItem)[0]
        path_params = [_deref_param(p, resolver, source) for p in item.parameters or []]
        for method, op in item.operations():
            op_params = [_deref_param(p, resolver, source) for p in op.parameters or []]
            merged: dict[tuple[str, str], RawParameter] = {}
            for p in [*path_params, *op_params]:
                merged[(str(p.name), str(p.in_))] = p
            consumes = op.consumes or root_consumes
            produces = op.produces or root_produces
            params: list[Parameter] = []
            body: RequestBody | None = None
            form_props: dict[str, Schema] = {}
            form_required: set[str] = set()
            form_has_file = False
            for p in merged.values():
                if p.in_ == "body":
                    schema = conv.convert(p.schema_ if p.schema_ is not None else True, source)
                    body = RequestBody(
                        content={media: schema for media in consumes},
                        required=bool(p.required),
                        description=p.description,
                        extensions=p.extensions,
                    )
                elif p.in_ == "formData":
                    name = str(p.name)
                    form_props[name] = conv.convert(p.swagger_schema(), source)
                    if p.required:
                        form_required.add(name)
                    form_has_file = form_has_file or p.type == "file"
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
            for code, resp in (op.responses or {}).items():
                if resp.ref:
                    resp = resolver.lookup_model(resp.ref, source, RawResponse)[0]
                content: dict[str, Schema] = {}
                if resp.schema_ is not None:
                    schema = conv.convert(resp.schema_, source)
                    content = {media: schema for media in produces}
                headers = {hname: conv.convert(_deref_header(h, resolver, source).swagger_schema(), source) for hname, h in (resp.headers or {}).items()}
                responses[code] = Response(
                    status=code,
                    description=resp.description,
                    content=content,
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
                    parameters=tuple(params),
                    request_body=body,
                    responses=responses,
                    deprecated=bool(op.deprecated),
                    extensions=op.extensions,
                )
            )

    return Document(
        title=doc.info.title or "",
        version=str(doc.info.version or ""),
        format="swagger2",
        source=source,
        hash=digest,
        description=doc.info.description,
        servers=servers,
        operations=tuple(operations),
        schemas=dict(conv.schemas),
        extensions=doc.extensions,
    )


def _deref_param(p: RawParameter, resolver: RefResolver, source: str) -> RawParameter:
    return resolver.lookup_model(p.ref, source, RawParameter)[0] if p.ref else p


def _deref_header(h: RawHeader, resolver: RefResolver, source: str) -> RawHeader:
    return resolver.lookup_model(h.ref, source, RawHeader)[0] if h.ref else h


def _parameter(p: RawParameter, conv: SchemaConverter, source: str) -> Parameter:
    loc = str(p.in_)
    style, explode = _COLLECTION_FORMATS.get(p.collection_format or "csv", ("form", False))
    if loc in ("path", "header"):
        style = "simple"
        explode = False
    elif p.type != "array":
        style, explode = "form", True
    return Parameter(
        name=str(p.name),
        location=loc,  # type: ignore[arg-type]
        schema=conv.convert(p.swagger_schema(), source),
        required=bool(p.required) or loc == "path",
        description=p.description,
        style=style,
        explode=explode,
        allow_reserved=bool(p.allow_reserved),
        extensions=p.extensions,
    )


__all__ = ["normalize_swagger2"]
