"""Normalised, immutable intermediate representation of an API description.

Both Swagger 2.0 and OpenAPI 3.x documents are converted into these nodes, so
the compiler never sees the source format. Nodes are frozen, slotted,
keyword-only **pydantic dataclasses**: pydantic v2 validates every field on
construction, while the objects keep dataclass semantics (``dataclasses.replace``,
equality, pickling for the on-disk IR cache).

References: ``Schema.ref`` names an entry in ``Document.schemas``. Every ``$ref``
is resolved at load time (including refs into other files, which are imported
into the document's schema table under a unique name); the name pointer is kept
because a flattened tree cannot represent recursive schemas.

Vendor extensions (``x-*``) are preserved verbatim in ``extensions`` on every
node; ``Operation.annotations`` is the slot plugins fill via ``annotate``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import field, replace
from typing import Any, Literal

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

Location = Literal["path", "query", "header", "cookie"]
Style = Literal["form", "simple", "matrix", "label", "spaceDelimited", "pipeDelimited", "tabDelimited", "deepObject"]

_CONFIG = ConfigDict(arbitrary_types_allowed=True)


def _dict() -> dict[str, Any]:
    return {}


def _str_dict() -> dict[str, str]:
    return {}


def _schemas() -> dict[str, Schema]:
    return {}


@dataclass(slots=True, frozen=True, kw_only=True, config=_CONFIG)
class Discriminator:
    property_name: str
    mapping: dict[str, str] = field(default_factory=_str_dict)  # value -> schema name


@dataclass(slots=True, frozen=True, kw_only=True, config=_CONFIG)
class Schema:
    """A JSON-Schema-like node.

    ``type`` is a single JSON type or ``None`` when the schema does not
    constrain the type (``{}``, pure ``allOf``, or a ``$ref``). ``nullable``
    covers OpenAPI 3.0 ``nullable``, Swagger ``x-nullable`` and 3.1 ``type:
    [T, "null"]``.
    """

    ref: str | None = None
    name: str | None = None
    title: str | None = None
    description: str | None = None
    type: str | None = None
    format: str | None = None
    nullable: bool = False
    properties: dict[str, Schema] = field(default_factory=_schemas)
    required: frozenset[str] = frozenset()
    items: Schema | None = None
    additional_properties: Schema | bool | None = None
    enum: tuple[Any, ...] | None = None
    const: Any = None
    has_const: bool = False
    default: Any = None
    has_default: bool = False
    all_of: tuple[Schema, ...] = ()
    one_of: tuple[Schema, ...] = ()
    any_of: tuple[Schema, ...] = ()
    discriminator: Discriminator | None = None
    read_only: bool = False
    write_only: bool = False
    deprecated: bool = False
    example: Any = None
    extensions: dict[str, Any] = field(default_factory=_dict)

    @property
    def is_ref(self) -> bool:
        return self.ref is not None


@dataclass(slots=True, frozen=True, kw_only=True, config=_CONFIG)
class Parameter:
    name: str
    location: Location
    schema: Schema
    required: bool = False
    description: str | None = None
    style: Style = "form"
    explode: bool = True
    allow_reserved: bool = False
    deprecated: bool = False
    extensions: dict[str, Any] = field(default_factory=_dict)


@dataclass(slots=True, frozen=True, kw_only=True, config=_CONFIG)
class RequestBody:
    content: dict[str, Schema]  # media type -> schema
    required: bool = False
    description: str | None = None
    extensions: dict[str, Any] = field(default_factory=_dict)

    @property
    def json_schema(self) -> Schema | None:
        for media, schema in self.content.items():
            if "json" in media:
                return schema
        return None


@dataclass(slots=True, frozen=True, kw_only=True, config=_CONFIG)
class Response:
    status: str  # "200", "2XX", "default"
    description: str | None = None
    content: dict[str, Schema] = field(default_factory=_schemas)
    headers: dict[str, Schema] = field(default_factory=_schemas)
    extensions: dict[str, Any] = field(default_factory=_dict)

    @property
    def json_schema(self) -> Schema | None:
        for media, schema in self.content.items():
            if "json" in media:
                return schema
        return None


@dataclass(slots=True, frozen=True, kw_only=True, config=_CONFIG)
class Server:
    url: str
    description: str | None = None
    variables: dict[str, str] = field(default_factory=_str_dict)  # name -> default
    extensions: dict[str, Any] = field(default_factory=_dict)


@dataclass(slots=True, frozen=True, kw_only=True, config=_CONFIG)
class Operation:
    operation_id: str
    method: str  # lower-case
    path: str
    summary: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    parameters: tuple[Parameter, ...] = ()
    request_body: RequestBody | None = None
    responses: dict[str, Response] = field(default_factory=_dict)
    deprecated: bool = False
    extensions: dict[str, Any] = field(default_factory=_dict)
    annotations: dict[str, Any] = field(default_factory=_dict)

    def annotated(self, **values: Any) -> Operation:
        """Return a copy with ``annotations`` updated (used by plugins)."""
        return replace(self, annotations={**self.annotations, **values})

    def success_responses(self) -> tuple[Response, ...]:
        return tuple(r for code, r in self.responses.items() if code.startswith("2") or code == "2XX")


@dataclass(slots=True, frozen=True, kw_only=True, config=_CONFIG)
class Document:
    title: str
    version: str
    format: Literal["swagger2", "openapi3", "jsonschema"]
    source: str  # path or URL the document was loaded from
    hash: str  # sha256 of the source bytes (+ loader version)
    description: str | None = None
    servers: tuple[Server, ...] = ()
    operations: tuple[Operation, ...] = ()
    schemas: dict[str, Schema] = field(default_factory=_schemas)
    extensions: dict[str, Any] = field(default_factory=_dict)
    annotations: dict[str, Any] = field(default_factory=_dict)

    def resolve(self, schema: Schema) -> Schema:
        """Follow ``ref`` pointers until a concrete schema is reached."""
        seen = 0
        while schema.ref is not None:
            schema = self.schemas[schema.ref]
            seen += 1
            if seen > 64:
                raise ValueError(f"reference cycle without a concrete schema: {schema.ref!r}")
        return schema

    def operation(self, operation_id: str) -> Operation:
        for op in self.operations:
            if op.operation_id == operation_id:
                return op
        raise KeyError(operation_id)

    def with_operations(self, operations: tuple[Operation, ...]) -> Document:
        return replace(self, operations=operations)

    def annotated(self, **values: Any) -> Document:
        return replace(self, annotations={**self.annotations, **values})

    def map_operations(self, fn: Callable[[Operation], Operation]) -> Document:
        return replace(self, operations=tuple(fn(op) for op in self.operations))


__all__ = ["Discriminator", "Document", "Location", "Operation", "Parameter", "RequestBody", "Response", "Schema", "Server", "Style"]
