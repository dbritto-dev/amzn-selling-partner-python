"""Normalised, immutable intermediate representation of an API description.

Both Swagger 2.0 and OpenAPI 3.x documents are converted into these nodes, so
the compiler never sees the source format. All nodes are frozen, slotted,
keyword-only dataclasses and are picklable (the on-disk IR cache stores them).

References: ``Schema.ref`` names an entry in ``Document.schemas``. Every ``$ref``
is resolved at load time (including refs into other files, which are imported
into the document's schema table under a unique name); the name pointer is kept
because a flattened tree cannot represent recursive schemas.

Vendor extensions (``x-*``) are preserved verbatim in ``extensions`` on every
node; ``Operation.annotations`` is the slot plugins fill via ``annotate``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal, TypeAlias

Location: TypeAlias = Literal["path", "query", "header", "cookie"]
Style: TypeAlias = Literal[
    "form",
    "simple",
    "matrix",
    "label",
    "spaceDelimited",
    "pipeDelimited",
    "tabDelimited",
    "deepObject",
]

_EMPTY: Mapping[str, Any] = {}


def _schemas() -> dict[str, Schema]:
    return {}


@dataclass(slots=True, frozen=True, kw_only=True)
class Discriminator:
    property_name: str
    mapping: Mapping[str, str] = field(default_factory=dict[str, str])  # value -> schema name


@dataclass(slots=True, frozen=True, kw_only=True)
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
    properties: Mapping[str, Schema] = field(default_factory=_schemas)
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
    extensions: Mapping[str, Any] = field(default_factory=dict[str, Any])

    @property
    def is_ref(self) -> bool:
        return self.ref is not None


@dataclass(slots=True, frozen=True, kw_only=True)
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
    extensions: Mapping[str, Any] = field(default_factory=dict[str, Any])


@dataclass(slots=True, frozen=True, kw_only=True)
class RequestBody:
    content: Mapping[str, Schema]  # media type -> schema
    required: bool = False
    description: str | None = None
    extensions: Mapping[str, Any] = field(default_factory=dict[str, Any])

    @property
    def json_schema(self) -> Schema | None:
        for media, schema in self.content.items():
            if "json" in media:
                return schema
        return None


@dataclass(slots=True, frozen=True, kw_only=True)
class Response:
    status: str  # "200", "2XX", "default"
    description: str | None = None
    content: Mapping[str, Schema] = field(default_factory=_schemas)
    headers: Mapping[str, Schema] = field(default_factory=_schemas)
    extensions: Mapping[str, Any] = field(default_factory=dict[str, Any])

    @property
    def json_schema(self) -> Schema | None:
        for media, schema in self.content.items():
            if "json" in media:
                return schema
        return None


@dataclass(slots=True, frozen=True, kw_only=True)
class Server:
    url: str
    description: str | None = None
    variables: Mapping[str, str] = field(default_factory=dict[str, str])  # name -> default
    extensions: Mapping[str, Any] = field(default_factory=dict[str, Any])


@dataclass(slots=True, frozen=True, kw_only=True)
class Operation:
    operation_id: str
    method: str  # lower-case
    path: str
    summary: str | None = None
    description: str | None = None
    tags: tuple[str, ...] = ()
    parameters: tuple[Parameter, ...] = ()
    request_body: RequestBody | None = None
    responses: Mapping[str, Response] = field(default_factory=dict[str, Response])
    deprecated: bool = False
    extensions: Mapping[str, Any] = field(default_factory=dict[str, Any])
    annotations: Mapping[str, Any] = field(default_factory=dict[str, Any])

    def annotated(self, **values: Any) -> Operation:
        """Return a copy with ``annotations`` updated (used by plugins)."""
        return replace(self, annotations={**self.annotations, **values})

    def success_responses(self) -> tuple[Response, ...]:
        return tuple(
            r for code, r in self.responses.items() if code.startswith("2") or code == "2XX"
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class Document:
    title: str
    version: str
    format: Literal["swagger2", "openapi3", "jsonschema"]
    source: str  # path or URL the document was loaded from
    hash: str  # sha256 of the source bytes (+ loader version)
    description: str | None = None
    servers: tuple[Server, ...] = ()
    operations: tuple[Operation, ...] = ()
    schemas: Mapping[str, Schema] = field(default_factory=_schemas)
    extensions: Mapping[str, Any] = field(default_factory=dict[str, Any])
    annotations: Mapping[str, Any] = field(default_factory=dict[str, Any])

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


__all__ = [
    "Discriminator",
    "Document",
    "Location",
    "Operation",
    "Parameter",
    "RequestBody",
    "Response",
    "Schema",
    "Server",
    "Style",
]
