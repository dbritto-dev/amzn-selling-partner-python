"""JSON-Schema dict -> ``Schema`` conversion shared by both normalisers."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping
from typing import Any

from .ir import Discriminator, Schema
from .refs import RefError, RefResolver

_SCHEMA_CONTAINERS = ("/definitions/", "/components/schemas/", "/$defs/")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_]")


def extensions_of(node: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in node.items() if k.startswith("x-")}


class SchemaConverter:
    """Converts schema dicts into IR ``Schema`` nodes, registering every named
    schema (local definitions and imported external ones) in ``schemas``."""

    def __init__(self, resolver: RefResolver) -> None:
        self.resolver = resolver
        self.schemas: dict[str, Schema] = {}
        self._in_progress: set[str] = set()
        self._ref_names: dict[tuple[str, str], str] = {}  # (uri, pointer) -> name

    # -- named schemas -------------------------------------------------------------

    def register_all(self, container: Mapping[str, Any] | None, uri: str, pointer_prefix: str) -> None:
        """Register every schema of a ``definitions`` / ``components.schemas`` map."""
        if not container:
            return
        for name in container:
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
            node = self.resolver.lookup(f"#{pointer}", uri)[0]
            if not isinstance(node, Mapping):
                raise RefError(f"schema {pointer!r} in {uri!r} is not an object")
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

    def convert(self, node: Mapping[str, Any] | bool, base_uri: str, *, name: str | None = None) -> Schema:
        if node is True or node == {}:
            return Schema(name=name)
        if node is False:
            return Schema(name=name, type="null")  # nothing validates; closest IR

        ref = node.get("$ref")
        if isinstance(ref, str):
            target_name = self.name_for_ref(ref, base_uri)
            if target_name is not None:
                extra = {k: v for k, v in node.items() if k != "$ref"}
                return Schema(
                    ref=target_name,
                    name=name,
                    description=extra.get("description"),
                    nullable=bool(extra.get("nullable") or extra.get("x-nullable")),
                    extensions=extensions_of(extra),
                )
            target, target_uri = self.resolver.lookup(ref, base_uri)
            if not isinstance(target, Mapping):
                raise RefError(f"$ref {ref!r} does not point at a schema object")
            return self.convert(target, target_uri, name=name)

        raw_type = node.get("type")
        nullable = bool(node.get("nullable") or node.get("x-nullable"))
        if isinstance(raw_type, list):
            types = [t for t in raw_type if t != "null"]
            nullable = nullable or len(types) != len(raw_type)
            type_ = types[0] if len(types) == 1 else None
        else:
            type_ = raw_type
        fmt = node.get("format")
        if type_ == "file":  # Swagger 2.0 formData file parameter
            type_, fmt = "string", "binary"

        properties: dict[str, Schema] = {}
        props = node.get("properties")
        if isinstance(props, Mapping):
            for pname, pnode in props.items():
                if isinstance(pnode, (Mapping, bool)):
                    properties[pname] = self.convert(pnode, base_uri)
        items = node.get("items")
        items_schema: Schema | None = None
        if isinstance(items, (Mapping, bool)):
            items_schema = self.convert(items, base_uri)
        elif isinstance(items, list):  # tuple validation: not representable, keep Any
            items_schema = Schema()

        additional: Schema | bool | None = None
        ap = node.get("additionalProperties")
        if isinstance(ap, bool):
            additional = ap
        elif isinstance(ap, Mapping):
            additional = self.convert(ap, base_uri)

        enum = node.get("enum")
        required = node.get("required")
        disc = node.get("discriminator")
        discriminator: Discriminator | None = None
        if isinstance(disc, str):
            discriminator = Discriminator(property_name=disc)
        elif isinstance(disc, Mapping) and isinstance(disc.get("propertyName"), str):
            mapping: dict[str, str] = {}
            for value, target in (disc.get("mapping") or {}).items():
                mapped = self.name_for_ref(str(target), base_uri) if isinstance(target, str) else None
                mapping[str(value)] = mapped if mapped is not None else str(target)
            discriminator = Discriminator(property_name=disc["propertyName"], mapping=mapping)

        example = node.get("example")
        if example is None and isinstance(node.get("examples"), list) and node["examples"]:
            example = node["examples"][0]

        return Schema(
            name=name,
            title=node.get("title"),
            description=node.get("description"),
            type=type_ if isinstance(type_, str) else None,
            format=fmt if isinstance(fmt, str) else None,
            nullable=nullable,
            properties=properties,
            required=frozenset(str(r) for r in required) if isinstance(required, list) else frozenset(),
            items=items_schema,
            additional_properties=additional,
            enum=tuple(enum) if isinstance(enum, list) else None,
            const=node.get("const"),
            has_const="const" in node,
            default=node.get("default"),
            has_default="default" in node,
            all_of=self._convert_list(node.get("allOf"), base_uri),
            one_of=self._convert_list(node.get("oneOf"), base_uri),
            any_of=self._convert_list(node.get("anyOf"), base_uri),
            discriminator=discriminator,
            read_only=bool(node.get("readOnly")),
            write_only=bool(node.get("writeOnly")),
            deprecated=bool(node.get("deprecated")),
            example=example,
            extensions=extensions_of(node),
        )

    def _convert_list(self, nodes: Any, base_uri: str) -> tuple[Schema, ...]:
        if not isinstance(nodes, list):
            return ()
        return tuple(self.convert(n, base_uri) for n in nodes if isinstance(n, (Mapping, bool)))


__all__ = ["SchemaConverter", "extensions_of"]
