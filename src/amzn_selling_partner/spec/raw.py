"""Pydantic v2 models of the source documents (Swagger 2.0, OpenAPI 3.x, JSON
Schema) as they appear on disk.

They validate the structure of a spec before normalisation and give the
normalisers typed access. Every model allows extra keys so vendor extensions
(``x-*``) survive (``extensions`` collects them) and unknown keywords never
break loading; values that vendors get wrong in practice are typed loosely.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_CONFIG = ConfigDict(extra="allow", frozen=True, populate_by_name=True)


class Node(BaseModel):
    model_config = _CONFIG

    @property
    def extensions(self) -> dict[str, Any]:
        extra = self.model_extra or {}
        return {k: v for k, v in extra.items() if k.startswith("x-")}

    @property
    def extra_keys(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class RawDiscriminator(Node):
    property_name: str = Field(alias="propertyName")
    mapping: dict[str, str] = Field(default_factory=dict)


class RawSchema(Node):
    """JSON-Schema-like node (Swagger 2.0 / OpenAPI 3.x / draft-07 subset)."""

    ref: str | None = Field(default=None, alias="$ref")
    ref_typo: str | None = Field(default=None, alias="#ref")  # seen in vendor schemas
    title: str | None = None
    description: str | None = None
    type: str | list[Any] | None = None
    format: Any = None
    nullable: bool | None = None
    x_nullable: bool | None = Field(default=None, alias="x-nullable")
    properties: dict[str, RawSchema | bool] | None = None
    required: list[Any] | bool | None = None
    items: RawSchema | bool | list[Any] | None = None
    additional_properties: RawSchema | bool | None = Field(default=None, alias="additionalProperties")
    enum: list[Any] | None = None
    const: Any = None
    default: Any = None
    all_of: list[RawSchema | bool] | None = Field(default=None, alias="allOf")
    one_of: list[RawSchema | bool] | None = Field(default=None, alias="oneOf")
    any_of: list[RawSchema | bool] | None = Field(default=None, alias="anyOf")
    discriminator: str | RawDiscriminator | None = None
    read_only: bool | None = Field(default=None, alias="readOnly")
    write_only: bool | None = Field(default=None, alias="writeOnly")
    deprecated: bool | None = None
    example: Any = None
    examples: Any = None
    definitions: dict[str, RawSchema | bool] | None = None
    defs: dict[str, RawSchema | bool] | None = Field(default=None, alias="$defs")

    @property
    def reference(self) -> str | None:
        return self.ref if self.ref is not None else self.ref_typo

    @property
    def has_const(self) -> bool:
        return "const" in self.model_fields_set

    @property
    def has_default(self) -> bool:
        return "default" in self.model_fields_set


class RawRef(Node):
    ref: str | None = Field(default=None, alias="$ref")


class RawMediaType(Node):
    schema_: RawSchema | bool | None = Field(default=None, alias="schema")
    example: Any = None
    examples: Any = None


class RawParameter(Node):
    ref: str | None = Field(default=None, alias="$ref")
    name: str | None = None
    in_: str | None = Field(default=None, alias="in")
    required: bool | None = None
    description: str | None = None
    deprecated: bool | None = None
    # OpenAPI 3
    schema_: RawSchema | bool | None = Field(default=None, alias="schema")
    content: dict[str, RawMediaType] | None = None
    style: str | None = None
    explode: bool | None = None
    allow_reserved: bool | None = Field(default=None, alias="allowReserved")
    # Swagger 2.0 (the schema keywords live on the parameter itself)
    type: str | None = None
    format: Any = None
    items: RawSchema | bool | None = None
    enum: list[Any] | None = None
    default: Any = None
    collection_format: str | None = Field(default=None, alias="collectionFormat")

    def swagger_schema(self) -> RawSchema:
        """The parameter's inline schema keywords as a ``RawSchema`` (Swagger 2.0)."""
        keys = {"type", "format", "items", "enum", "default", "minimum", "maximum", "pattern", "minLength", "maxLength", "minItems", "maxItems", "uniqueItems", "multipleOf", "x-nullable", "description"}
        data = {k: v for k, v in self.model_dump(by_alias=True, exclude_none=True).items() if k in keys}
        return RawSchema.model_validate(data)


class RawHeader(Node):
    ref: str | None = Field(default=None, alias="$ref")
    description: str | None = None
    schema_: RawSchema | bool | None = Field(default=None, alias="schema")
    type: str | None = None
    format: Any = None
    items: RawSchema | bool | None = None
    enum: list[Any] | None = None

    def swagger_schema(self) -> RawSchema:
        data = {k: v for k, v in self.model_dump(by_alias=True, exclude_none=True).items() if k in {"type", "format", "items", "enum", "description"}}
        return RawSchema.model_validate(data)


class RawRequestBody(Node):
    ref: str | None = Field(default=None, alias="$ref")
    description: str | None = None
    required: bool | None = None
    content: dict[str, RawMediaType] | None = None


class RawResponse(Node):
    ref: str | None = Field(default=None, alias="$ref")
    description: str | None = None
    schema_: RawSchema | bool | None = Field(default=None, alias="schema")  # Swagger 2.0
    content: dict[str, RawMediaType] | None = None  # OpenAPI 3
    headers: dict[str, RawHeader] | None = None


class RawOperation(Node):
    operation_id: str | None = Field(default=None, alias="operationId")
    summary: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    parameters: list[RawParameter] | None = None
    request_body: RawRequestBody | None = Field(default=None, alias="requestBody")
    responses: dict[str, RawResponse] | None = None
    deprecated: bool | None = None
    consumes: list[str] | None = None
    produces: list[str] | None = None


class RawPathItem(Node):
    ref: str | None = Field(default=None, alias="$ref")
    parameters: list[RawParameter] | None = None
    get: RawOperation | None = None
    put: RawOperation | None = None
    post: RawOperation | None = None
    delete: RawOperation | None = None
    options: RawOperation | None = None
    head: RawOperation | None = None
    patch: RawOperation | None = None
    trace: RawOperation | None = None

    def operations(self) -> list[tuple[str, RawOperation]]:
        out: list[tuple[str, RawOperation]] = []
        for method in ("get", "put", "post", "delete", "options", "head", "patch", "trace"):
            op = getattr(self, method)
            if op is not None:
                out.append((method, op))
        return out


class RawInfo(Node):
    title: str | None = None
    version: Any = None
    description: str | None = None


class RawServerVariable(Node):
    default: Any = None
    enum: list[Any] | None = None
    description: str | None = None


class RawServer(Node):
    url: str = ""
    description: str | None = None
    variables: dict[str, RawServerVariable] | None = None


class RawComponents(Node):
    schemas: dict[str, RawSchema | bool] | None = None
    parameters: dict[str, RawParameter] | None = None
    responses: dict[str, RawResponse] | None = None
    request_bodies: dict[str, RawRequestBody] | None = Field(default=None, alias="requestBodies")
    headers: dict[str, RawHeader] | None = None


class SwaggerDocument(Node):
    swagger: str
    info: RawInfo = Field(default_factory=RawInfo)
    host: str | None = None
    base_path: str | None = Field(default=None, alias="basePath")
    schemes: list[str] | None = None
    consumes: list[str] | None = None
    produces: list[str] | None = None
    paths: dict[str, RawPathItem] = Field(default_factory=dict)
    definitions: dict[str, RawSchema | bool] | None = None
    parameters: dict[str, RawParameter] | None = None
    responses: dict[str, RawResponse] | None = None


class OpenAPIDocument(Node):
    openapi: str
    info: RawInfo = Field(default_factory=RawInfo)
    servers: list[RawServer] | None = None
    paths: dict[str, RawPathItem] = Field(default_factory=dict)
    components: RawComponents | None = None


__all__ = [
    "Node",
    "OpenAPIDocument",
    "RawComponents",
    "RawDiscriminator",
    "RawHeader",
    "RawInfo",
    "RawMediaType",
    "RawOperation",
    "RawParameter",
    "RawPathItem",
    "RawRef",
    "RawRequestBody",
    "RawResponse",
    "RawSchema",
    "RawServer",
    "SwaggerDocument",
]
