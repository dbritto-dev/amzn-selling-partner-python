"""Operation -> ``CompiledOp``.

A ``CompiledOp`` holds everything the runtime needs to execute one operation
without looking at the spec again: the URL template, ordered parameter
serializers, the body encoder, prebuilt ``TypeAdapter``s per success status,
the error adapter, an ``inspect.Signature`` of keyword-only parameters, the
rate-limit annotation and the (detected or overridden) pagination descriptor.

Pagination detection (API-agnostic heuristic, see ``detect_pagination``)::

  * a query parameter named nextToken / pageToken / paginationToken
    (case-insensitive),
  * a same-named or ``nextToken`` string field in the success schema at the
    top level, under ``payload``, under ``pagination`` or under
    ``payload.pagination``,
  * exactly one array field in that container (or, failing that, in its
    parent), ignoring a field named ``errors``.

Anything else is logged and left unpaginated; plugins may override through
``Operation.annotations["pagination"]``.
"""

from __future__ import annotations

import inspect
import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Literal, cast
from urllib.parse import urlencode

from pydantic import BaseModel, TypeAdapter
from pydantic_core import to_json

from ..runtime._pagination import CompiledPagination, Pagination, make_getter
from ..runtime._throttle import RateLimit
from ..runtime._types import NOT_GIVEN
from ..spec.ir import Document, Operation, Parameter, Response, Schema
from ._serializers import Encoder, header_serializer, path_serializer, query_serializer
from .models import ModelNamespace
from .naming import field_name, method_name, param_name, pascal_case
from .typenames import type_expr

log = logging.getLogger("amzn_selling_partner.compile.operations")

_PATH_PARAM = re.compile(r"\{([^{}]+)\}")
_TOKEN_NAMES = frozenset({"nexttoken", "pagetoken", "paginationtoken"})
_CONTAINERS = ("payload", "pagination")

BodyKind = Literal["json", "binary", "text", "form", "multipart"]
DecodeKind = Literal["json", "bytes", "text", "none"]


@dataclass(slots=True, frozen=True)
class ParamSpec:
    py_name: str
    wire_name: str
    required: bool
    location: str
    encode: Encoder = field(repr=False)
    annotation: str = field(repr=False, default="Any")


@dataclass(slots=True)
class BodySpec:
    kind: BodyKind
    content_type: str
    required: bool
    annotation: str = "Any"  # type expression for signatures/stubs
    schema: Schema | None = field(repr=False, default=None)
    ns: ModelNamespace | None = field(repr=False, default=None)
    _type: Any = field(repr=False, default=None)

    @property
    def python_type(self) -> Any:
        """The body's python type (models are built on first access)."""
        if self._type is None:
            assert self.ns is not None and self.schema is not None
            self._type = self.ns.type_for(self.schema, name_hint=self.annotation)
        return self._type


@dataclass(slots=True)
class Decoder:
    kind: DecodeKind
    annotation: str = "None"
    schema: Schema | None = field(repr=False, default=None)
    ns: ModelNamespace | None = field(repr=False, default=None)
    hint: str = field(repr=False, default="Response")
    _adapter: TypeAdapter[Any] | None = field(repr=False, default=None)

    @property
    def adapter(self) -> TypeAdapter[Any]:
        """Prebuilt on first use: ``TypeAdapter`` over the response type."""
        ad = self._adapter
        if ad is None:
            assert self.ns is not None and self.schema is not None
            ad = self.ns.adapter(self.schema, name_hint=self.hint)
            self._adapter = ad
        return ad

    @property
    def python_type(self) -> Any:
        if self.kind == "json":
            assert self.ns is not None and self.schema is not None
            return self.ns.type_for(self.schema, name_hint=self.hint)
        return {"bytes": bytes, "text": str}.get(self.kind, type(None))

    def decode(self, body: bytes, text: Callable[[], str]) -> Any:
        if self.kind == "json":
            ad = self._adapter
            if ad is None:
                ad = self.adapter
            return ad.validate_json(body)
        if self.kind == "bytes":
            return body
        if self.kind == "text":
            return text()
        return None

    def warm(self) -> None:
        if self.kind == "json":
            self.adapter  # noqa: B018


@dataclass(slots=True, frozen=True, kw_only=True)
class CompiledOp:
    key: str
    name: str
    operation_id: str
    method: str  # upper-case
    path: str
    url_template: str  # str.format template with positional placeholders
    static_path: bool
    path_params: tuple[ParamSpec, ...]
    query_params: tuple[ParamSpec, ...]
    header_params: tuple[ParamSpec, ...]
    body: BodySpec | None
    accepted: frozenset[str]  # every python kwarg the op understands (excluding options)
    required: tuple[str, ...]
    signature: inspect.Signature = field(repr=False)
    decoders: dict[int, Decoder] = field(repr=False)
    default_decoder: Decoder = field(repr=False)
    error_decoders: dict[int, Decoder] = field(repr=False)
    default_error: Decoder | None = field(repr=False)
    stream_default: bool
    rate_limit: RateLimit | None
    pagination: CompiledPagination | None
    doc: str | None = field(repr=False)
    extensions: dict[str, Any] = field(repr=False)
    annotations: dict[str, Any] = field(repr=False)
    ir: Operation = field(repr=False)
    tags: tuple[str, ...] = ()

    # -- request building (hot path) ------------------------------------------------

    def build_url(self, base_url: str, kwargs: dict[str, Any]) -> str:
        if self.static_path:
            url = base_url + self.url_template
        else:
            url = base_url + self.url_template.format(*[p.encode(kwargs[p.py_name]) for p in self.path_params])
        if self.query_params:
            parts: list[str] = []
            for p in self.query_params:
                v = kwargs.get(p.py_name, NOT_GIVEN)
                if v is not NOT_GIVEN and v is not None:
                    parts.append(p.encode(v))
            if parts:
                url = url + "?" + "&".join(parts)
        return url

    def build_headers(self, kwargs: dict[str, Any]) -> tuple[tuple[str, str], ...]:
        return tuple(
            (p.wire_name, p.encode(kwargs[p.py_name]))
            for p in self.header_params
            if kwargs.get(p.py_name, NOT_GIVEN) is not NOT_GIVEN and kwargs[p.py_name] is not None
        )

    def encode_body(self, value: Any) -> tuple[bytes, str] | None:
        body = self.body
        if body is None:
            return None
        if value is NOT_GIVEN:
            if body.required:
                raise TypeError(f"{self.name}() missing required argument: 'body'")
            return None
        if body.kind == "json":
            if isinstance(value, BaseModel):
                return value.__pydantic_serializer__.to_json(value, by_alias=True, exclude_none=True), body.content_type
            return to_json(value, by_alias=True, exclude_none=True), body.content_type
        if body.kind == "binary":
            if isinstance(value, str):
                value = value.encode()
            return bytes(value), body.content_type
        if body.kind == "text":
            return (value if isinstance(value, bytes) else str(value).encode()), body.content_type
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(cast(bytes, value)), body.content_type  # pre-encoded form/multipart payload
        if body.kind == "form" and isinstance(value, dict):
            return urlencode(cast(dict[str, Any], value), doseq=True).encode(), body.content_type
        raise TypeError(f"{self.name}: a {body.kind!r} body must be passed as pre-encoded bytes")

    def check_kwargs(self, kwargs: dict[str, Any]) -> None:
        keys = kwargs.keys()
        if not keys <= self.accepted:
            unexpected = sorted(keys - self.accepted)
            raise TypeError(f"{self.name}() got unexpected keyword argument(s): {', '.join(unexpected)}")
        for r in self.required:
            if r not in kwargs or kwargs[r] is NOT_GIVEN:
                raise TypeError(f"{self.name}() missing required keyword argument: {r!r}")

    def decoder_for(self, status: int) -> Decoder:
        d = self.decoders.get(status)
        return d if d is not None else self.default_decoder

    def warm(self) -> None:
        """Build every adapter/model this operation needs (preload)."""
        for d in self.decoders.values():
            d.warm()
        self.default_decoder.warm()
        for d in self.error_decoders.values():
            d.warm()
        if self.default_error is not None:
            self.default_error.warm()
        if self.body is not None and self.body.kind == "json":
            self.body.python_type  # noqa: B018

    @property
    def returns_page(self) -> bool:
        return self.pagination is not None


# -- compilation -------------------------------------------------------------------


def compile_operation(
    op: Operation,
    document: Document,
    ns: ModelNamespace,
    *,
    key_prefix: str,
    name: str | None = None,
) -> CompiledOp:
    resolve = document.resolve
    py_names: set[str] = set()

    def unique(py: str) -> str:
        cand = py
        n = 2
        while cand in py_names:
            cand = f"{py}_{n}"
            n += 1
        py_names.add(cand)
        return cand

    path_specs: list[ParamSpec] = []
    query_specs: list[ParamSpec] = []
    header_specs: list[ParamSpec] = []

    def ann(schema: Schema, hint: str) -> str:
        return type_expr(document, schema, hint, model_prefix="models.")

    by_wire: dict[tuple[str, str], Parameter] = {(p.name, p.location): p for p in op.parameters}
    # path params in the order they appear in the template
    template = op.path
    ordered_path: list[str] = _PATH_PARAM.findall(op.path)
    for wire in ordered_path:
        p = by_wire.get((wire, "path"))
        if p is None:
            p = Parameter(name=wire, location="path", schema=Schema(type="string"), required=True)
        path_specs.append(
            ParamSpec(unique(param_name(wire)), wire, True, "path", path_serializer(p, resolve), ann(p.schema, pascal_case(wire)))
        )
        template = template.replace("{" + wire + "}", "{}", 1)
    for p in op.parameters:
        if p.location == "query":
            query_specs.append(
                ParamSpec(
                    unique(param_name(p.name)),
                    p.name,
                    p.required,
                    "query",
                    query_serializer(p, resolve),
                    ann(p.schema, pascal_case(p.name)),
                )
            )
        elif p.location == "header":
            header_specs.append(
                ParamSpec(
                    unique(param_name(p.name)),
                    p.name,
                    p.required,
                    "header",
                    header_serializer(p, resolve),
                    ann(p.schema, pascal_case(p.name)),
                )
            )
        elif p.location == "cookie":
            log.warning("%s.%s: cookie parameter %r is not supported and is ignored", key_prefix, op.operation_id, p.name)

    body_spec: BodySpec | None = None
    if op.request_body is not None:
        media, schema = next(iter(op.request_body.content.items()), ("application/json", Schema()))
        for m, s in op.request_body.content.items():
            if "json" in m:
                media, schema = m, s
                break
        hint = pascal_case(op.operation_id) + "Body"
        if "json" in media:
            body_spec = BodySpec("json", media, op.request_body.required, ann(schema, hint), schema, ns)
        elif media == "multipart/form-data":
            body_spec = BodySpec("multipart", media, op.request_body.required, "bytes | dict[str, Any]")
        elif media == "application/x-www-form-urlencoded":
            body_spec = BodySpec("form", media, op.request_body.required, "bytes | dict[str, Any]")
        elif media.startswith("text/"):
            body_spec = BodySpec("text", media, op.request_body.required, "str")
        else:
            body_spec = BodySpec("binary", media, op.request_body.required, "bytes")
        py_names.add("body")

    decoders: dict[int, Decoder] = {}
    default_decoder = Decoder("none")
    error_decoders: dict[int, Decoder] = {}
    default_error: Decoder | None = None
    stream_default = False
    first_success: Decoder | None = None
    for code, resp in op.responses.items():
        if code == "default":
            js = resp.json_schema
            if js is not None:
                default_error = Decoder("json", ann(js, "Error"), js, ns, "Error")
            continue
        try:
            status = int(code.replace("X", "0"))
        except ValueError:
            continue
        if 200 <= status < 300:
            dec = _decoder(resp, ns, op.operation_id, document)
            if any(m == "text/event-stream" for m in resp.content) and first_success is None:
                stream_default = True
            decoders[status] = dec
            if first_success is None:
                first_success = dec
        else:
            js = resp.json_schema
            if js is not None:
                error_decoders[status] = Decoder("json", ann(js, "Error"), js, ns, "Error")
    if first_success is not None:
        default_decoder = first_success
    if default_error is None and error_decoders:
        # most specs reuse one error shape; use the 400 one (or any) as the fallback
        default_error = error_decoders.get(400) or next(iter(error_decoders.values()))

    # signature ----------------------------------------------------------------------
    params: list[inspect.Parameter] = []
    for spec in [*path_specs, *query_specs, *header_specs]:
        default = inspect.Parameter.empty if spec.required else NOT_GIVEN
        annotation = spec.annotation if spec.required else f"{spec.annotation} | NotGiven"
        params.append(inspect.Parameter(spec.py_name, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=annotation))
    if body_spec is not None:
        default = inspect.Parameter.empty if body_spec.required else NOT_GIVEN
        params.append(inspect.Parameter("body", inspect.Parameter.KEYWORD_ONLY, default=default, annotation=body_spec.annotation))
    params.append(inspect.Parameter("raw", inspect.Parameter.KEYWORD_ONLY, default=False, annotation="bool"))
    params.append(
        inspect.Parameter("paginate", inspect.Parameter.KEYWORD_ONLY, default=NOT_GIVEN, annotation="Pagination | None | NotGiven")
    )
    params.append(inspect.Parameter("request_options", inspect.Parameter.KEYWORD_ONLY, default=None, annotation="RequestOptions | None"))
    # keep signature parameters ordered: required first
    params.sort(key=lambda p: p.default is not inspect.Parameter.empty)
    signature = inspect.Signature(params, return_annotation=default_decoder.annotation)

    required = tuple(s.py_name for s in [*path_specs, *query_specs, *header_specs] if s.required)
    if body_spec is not None and body_spec.required:
        required = (*required, "body")
    accepted = frozenset(py_names)

    # annotations from plugins ---------------------------------------------------------
    rate_limit = op.annotations.get("rate_limit")
    if rate_limit is not None and not isinstance(rate_limit, RateLimit):
        raise TypeError(f"{op.operation_id}: rate_limit annotation must be a RateLimit")
    pagination_desc: Pagination | None
    if "pagination" in op.annotations:
        pagination_desc = op.annotations["pagination"]  # may be None to force off
    else:
        pagination_desc = detect_pagination(op, document, key=f"{key_prefix}.{op.operation_id}")
    compiled_pagination = compile_pagination(pagination_desc, query_specs, path_specs, header_specs) if pagination_desc else None

    key = f"{key_prefix}.{op.operation_id}"
    return CompiledOp(
        key=key,
        name=name or method_name(op.operation_id),
        operation_id=op.operation_id,
        method=op.method.upper(),
        path=op.path,
        url_template=template,
        static_path=not path_specs,
        path_params=tuple(path_specs),
        query_params=tuple(query_specs),
        header_params=tuple(header_specs),
        body=body_spec,
        accepted=accepted,
        required=required,
        signature=signature,
        decoders=decoders,
        default_decoder=default_decoder,
        error_decoders=error_decoders,
        default_error=default_error,
        stream_default=stream_default,
        rate_limit=rate_limit,
        pagination=compiled_pagination,
        doc=_docstring(op),
        extensions=dict(op.extensions),
        annotations=dict(op.annotations),
        ir=op,
        tags=op.tags,
    )


def compile_operations(document: Document, ns: ModelNamespace, *, key_prefix: str) -> list[CompiledOp]:
    """Compile every operation of a document, de-duplicating method names
    (a repeated operationId gets the HTTP method appended)."""
    seen: dict[str, int] = {}
    out: list[CompiledOp] = []
    for op in document.operations:
        base = method_name(op.operation_id)
        name = base
        if base in seen:
            name = f"{base}_{op.method.lower()}"
            if name in seen:
                seen[name] = seen.get(name, 0) + 1
                name = f"{name}_{seen[name]}"
            log.warning(
                "%s: duplicate operationId %r; exposing %s %s as %s()", key_prefix, op.operation_id, op.method.upper(), op.path, name
            )
        seen[name] = seen.get(name, 0) + 1
        out.append(compile_operation(op, document, ns, key_prefix=key_prefix, name=name))
    return out


def _decoder(resp: Response, ns: ModelNamespace, op_id: str, document: Document) -> Decoder:
    js = resp.json_schema
    if js is not None:
        hint = pascal_case(op_id) + "Response"
        return Decoder("json", type_expr(document, js, hint, model_prefix="models."), js, ns, hint)
    if not resp.content:
        return Decoder("none")
    media = next(iter(resp.content))
    if media.startswith("text/"):
        return Decoder("text", "str")
    return Decoder("bytes", "bytes")


def _docstring(op: Operation) -> str:
    parts: list[str] = []
    if op.summary:
        parts.append(op.summary.strip())
    if op.description:
        parts.append(op.description.strip())
    parts.append(f"{op.method.upper()} {op.path}")
    return "\n\n".join(parts)


# -- pagination -------------------------------------------------------------------------


def detect_pagination(op: Operation, document: Document, *, key: str = "") -> Pagination | None:
    token_param = next((p for p in op.parameters if p.location == "query" and p.name.lower() in _TOKEN_NAMES), None)
    if token_param is None:
        return None
    success = next((r for c, r in op.responses.items() if c.startswith("2")), None)
    if success is None or success.json_schema is None:
        log.info("pagination: %s has a %s parameter but no JSON success schema; left unpaginated", key, token_param.name)
        return None
    root = _props(document, success.json_schema)
    if root is None:
        return None
    candidates: list[tuple[str, str, str | None]] = []  # (token_path, items_path, prev_path)
    containers: list[tuple[str, dict[str, Schema], dict[str, Schema] | None]] = [("", root, None)]
    for c in _CONTAINERS:
        sub = root.get(c)
        if sub is not None:
            sub_props = _props(document, sub)
            if sub_props is not None:
                containers.append((c, sub_props, root))
                if c == "payload":
                    pag = sub_props.get("pagination")
                    pag_props = _props(document, pag) if pag is not None else None
                    if pag_props is not None:
                        containers.append(("payload.pagination", pag_props, sub_props))
    wanted = {token_param.name.lower(), "nexttoken"}
    for prefix, props, parent in containers:
        token_field = next((n for n, s in props.items() if n.lower() in wanted and document.resolve(s).type in ("string", None)), None)
        if token_field is None:
            continue
        arrays = [n for n, s in props.items() if document.resolve(s).type == "array" and n != "errors"]
        if not arrays and parent is not None:
            arrays = [n for n, s in parent.items() if document.resolve(s).type == "array" and n != "errors"]
            items_prefix = prefix.rsplit(".", 1)[0] if "." in prefix else ""
        else:
            items_prefix = prefix
        prev_field = next((n for n in props if n.lower() in ("prevtoken", "previoustoken", "previouspagetoken")), None)
        if len(arrays) == 1:
            candidates.append(
                (_join(prefix, token_field), _join(items_prefix, arrays[0]), _join(prefix, prev_field) if prev_field else None)
            )
        else:
            log.info(
                "pagination: %s: token field %r found but %d array fields nearby (%s); left unpaginated",
                key,
                _join(prefix, token_field),
                len(arrays),
                ", ".join(arrays) or "none",
            )
            return None
    if len(candidates) != 1:
        if candidates:
            log.info("pagination: %s: ambiguous (%d candidates); left unpaginated", key, len(candidates))
        else:
            log.info(
                "pagination: %s has a %s parameter but no matching token field in the response; left unpaginated", key, token_param.name
            )
        return None
    token_path, items_path, prev_path = candidates[0]
    return Pagination(
        items_path=items_path,
        next_token_path=token_path,
        next_token_param=token_param.name,
        prev_token_path=prev_path,
        source="heuristic",
    )


def _join(prefix: str, name: str) -> str:
    return f"{prefix}.{name}" if prefix else name


def _props(document: Document, schema: Schema | None) -> dict[str, Schema] | None:
    if schema is None:
        return None
    s = document.resolve(schema)
    if s.all_of:
        merged: dict[str, Schema] = {}
        for part in s.all_of:
            sub = _props(document, part)
            if sub:
                merged.update(sub)
        merged.update(s.properties)
        return merged or None
    if s.properties:
        return dict(s.properties)
    return None


def compile_pagination(
    desc: Pagination,
    query_specs: Iterable[ParamSpec],
    path_specs: Iterable[ParamSpec],
    header_specs: Iterable[ParamSpec],
) -> CompiledPagination:
    wire_to_py = {s.wire_name: s.py_name for s in [*query_specs, *header_specs]}
    token_kw = wire_to_py.get(desc.next_token_param)
    if token_kw is None:
        raise ValueError(f"pagination: next_token_param {desc.next_token_param!r} is not a query/header parameter")
    keep = {s.py_name for s in path_specs} | {wire_to_py[w] for w in desc.keep_params if w in wire_to_py}
    return CompiledPagination(
        descriptor=desc,
        token_kw=token_kw,
        keep_kws=frozenset(keep),
        items_model=make_getter(desc.items_path, python_names=field_name),
        token_model=make_getter(desc.next_token_path, python_names=field_name),
        prev_model=make_getter(desc.prev_token_path, python_names=field_name) if desc.prev_token_path else None,
        items_raw=make_getter(desc.items_path),
        token_raw=make_getter(desc.next_token_path),
        prev_raw=make_getter(desc.prev_token_path) if desc.prev_token_path else None,
    )


__all__ = [
    "BodySpec",
    "CompiledOp",
    "Decoder",
    "ParamSpec",
    "compile_operation",
    "compile_operations",
    "compile_pagination",
    "detect_pagination",
]
