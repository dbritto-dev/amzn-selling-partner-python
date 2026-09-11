"""``RawSchema`` (pydantic model of the on-disk schema) -> IR ``Schema`` conversion
shared by both normalisers."""

from __future__ import annotations

import logging
import posixpath
import re
from collections.abc import Iterable
from typing import Any, cast

from .ir import Discriminator, Schema
from .raw import Node, RawDiscriminator, RawSchema
from .refs import RefError, RefResolver

log = logging.getLogger("amzn_selling_partner.spec")

_SCHEMA_CONTAINERS = ("/definitions/", "/components/schemas/", "/$defs/")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_]")


def extensions_of(node: Node) -> dict[str, Any]:
    return node.extensions


def _enum_values(value: list[Any] | None) -> tuple[Any, ...] | None:
    return tuple(value) if value is not None else None


class SchemaConverter:
    """Converts raw schema nodes into IR ``Schema`` nodes, registering every
    named schema (local definitions and imported external ones) in ``schemas``."""

    def __init__(self, resolver: RefResolver) -> None:
        self.resolver = resolver
        self.schemas: dict[str, Schema] = {}
        self._in_progress: set[str] = set()
        self._ref_names: dict[tuple[str, str], str] = {}  # (uri, pointer) -> name
        self.dangling_refs: list[str] = []

    # -- named schemas -------------------------------------------------------------

    def register_all(self, names: Iterable[str] | None, uri: str, pointer_prefix: str) -> None:
        """Register every schema of a ``definitions`` / ``components.schemas`` map."""
        for name in names or ():
            self.ensure_named(name, uri, f"{pointer_prefix}/{name}")

    def ensure_named(self, name: str, uri: str, pointer: str) -> str:
        key = (uri, pointer)
        existing = self._ref_names.get(key)
        if existing is not None:
            return existing
        if name in self.schemas or name in self._in_progress:
            # Same name from another document: disambiguate with the file stem.
            stem = _SAFE_NAME.sub("_", posixpath.splitext(posixpath.basename(uri))[0])
            candidate = f"{stem}_{name}"
            n = 2
            while candidate in self.schemas or candidate in self._in_progress:
                candidate = f"{stem}_{name}_{n}"
                n += 1
            name = candidate
        self._ref_names[key] = name
        self._in_progress.add(name)
        try:
            node = self.resolver.lookup_schema(f"#{pointer}", uri)[0]
            self.schemas[name] = self.convert(node, uri, name=name)
        finally:
            self._in_progress.discard(name)
        return name

    def name_for_ref(self, ref: str, base_uri: str) -> str | None:
        """Return the registered name for a ``$ref`` that targets a named schema,
        registering it first if needed; ``None`` for refs into arbitrary pointers."""
        uri, pointer = self.resolver.split(ref, base_uri)
        for container in _SCHEMA_CONTAINERS:
            head, sep, tail = pointer.partition(container)
            if sep and tail and "/" not in tail and head == "":
                return self.ensure_named(tail.replace("~1", "/").replace("~0", "~"), uri, pointer)
        return None

    # -- conversion ----------------------------------------------------------------

    def convert(self, node: RawSchema | bool, base_uri: str, *, name: str | None = None) -> Schema:
        if node is True:
            return Schema(name=name)
        if node is False:
            return Schema(name=name, type="null")  # nothing validates; closest IR
        if not node.model_fields_set and not node.model_extra:
            return Schema(name=name)

        ref = node.reference
        if ref is not None:
            if node.ref is None:
                log.warning("%s: '#ref' used instead of '$ref' (%s); accepting it", base_uri, ref)
            try:
                target_name = self.name_for_ref(ref, base_uri)
            except RefError as exc:
                # dangling reference (seen in vendor schemas): keep loading, type as Any
                log.warning("%s: %s; treating as untyped", base_uri, exc)
                self.dangling_refs.append(ref)
                return Schema(name=name, description=node.description, extensions=node.extensions)
            if target_name is not None:
                return Schema(
                    ref=target_name,
                    name=name,
                    description=node.description,
                    nullable=bool(node.nullable or node.x_nullable),
                    extensions=node.extensions,
                )
            target, target_uri = self.resolver.lookup_schema(ref, base_uri)
            return self.convert(target, target_uri, name=name)

        nullable = bool(node.nullable or node.x_nullable)
        type_: str | None
        if isinstance(node.type, list):
            types = [t for t in node.type if t != "null"]
            nullable = nullable or len(types) != len(node.type)
            type_ = str(types[0]) if len(types) == 1 else None
        else:
            type_ = node.type
        fmt = node.format if isinstance(node.format, str) else None
        if type_ == "file":  # Swagger 2.0 formData file parameter
            type_, fmt = "string", "binary"

        properties = {pname: self.convert(pnode, base_uri) for pname, pnode in (node.properties or {}).items()}
        items_schema: Schema | None = None
        if isinstance(node.items, (RawSchema, bool)):
            items_schema = self.convert(node.items, base_uri)
        elif isinstance(node.items, list):  # tuple validation: not representable, keep Any
            items_schema = Schema()

        additional: Schema | bool | None = None
        if isinstance(node.additional_properties, bool):
            additional = node.additional_properties
        elif isinstance(node.additional_properties, RawSchema):
            additional = self.convert(node.additional_properties, base_uri)

        discriminator: Discriminator | None = None
        if isinstance(node.discriminator, str):
            discriminator = Discriminator(property_name=node.discriminator)
        elif isinstance(node.discriminator, RawDiscriminator):
            mapping: dict[str, str] = {}
            for value, target in node.discriminator.mapping.items():
                mapped = self.name_for_ref(target, base_uri)
                mapping[value] = mapped if mapped is not None else target
            discriminator = Discriminator(property_name=node.discriminator.property_name, mapping=mapping)

        example: Any = node.example
        examples: Any = node.examples
        if example is None and isinstance(examples, list) and examples:
            example = cast(list[Any], examples)[0]

        return Schema(
            name=name,
            title=node.title,
            description=node.description,
            type=type_,
            format=fmt,
            nullable=nullable,
            properties=properties,
            required=frozenset(str(r) for r in node.required) if isinstance(node.required, list) else frozenset(),
            items=items_schema,
            additional_properties=additional,
            enum=_enum_values(node.enum),
            const=node.const,
            has_const=node.has_const,
            default=node.default,
            has_default=node.has_default,
            all_of=self._convert_list(node.all_of, base_uri),
            one_of=self._convert_list(node.one_of, base_uri),
            any_of=self._convert_list(node.any_of, base_uri),
            discriminator=discriminator,
            read_only=bool(node.read_only),
            write_only=bool(node.write_only),
            deprecated=bool(node.deprecated),
            example=example,
            extensions=node.extensions,
        )

    def _convert_list(self, nodes: list[RawSchema | bool] | None, base_uri: str) -> tuple[Schema, ...]:
        return tuple(self.convert(n, base_uri) for n in nodes or ())


__all__ = ["SchemaConverter", "extensions_of"]
