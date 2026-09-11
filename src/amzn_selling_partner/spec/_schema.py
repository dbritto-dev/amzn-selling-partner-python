"""JSON-Schema dict -> ``Schema`` conversion shared by both normalisers."""

from __future__ import annotations

import logging
import posixpath
import re
from collections.abc import Mapping
from typing import Any, cast

from ._jsonutil import JsonObject, as_list, as_object, obj, text
from .ir import Discriminator, Schema
from .refs import RefError, RefResolver

log = logging.getLogger("amzn_selling_partner.spec")

_SCHEMA_CONTAINERS = ("/definitions/", "/components/schemas/", "/$defs/")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_]")


def extensions_of(node: Mapping[str, Any]) -> dict[str, Any]:
    return {str(k): v for k, v in node.items() if str(k).startswith("x-")}


def _enum_values(value: Any) -> tuple[Any, ...] | None:
    if not isinstance(value, list):
        return None
    return tuple(as_list(cast(Any, value)))


class SchemaConverter:
    """Converts schema dicts into IR ``Schema`` nodes, registering every named
    schema (local definitions and imported external ones) in ``schemas``."""

    def __init__(self, resolver: RefResolver) -> None:
        self.resolver = resolver
        self.schemas: dict[str, Schema] = {}
        self._in_progress: set[str] = set()
        self._ref_names: dict[tuple[str, str], str] = {}  # (uri, pointer) -> name
        self.dangling_refs: list[str] = []

    # -- named schemas -------------------------------------------------------------

    def register_all(self, container: JsonObject | None, uri: str, pointer_prefix: str) -> None:
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
            node = self.resolver.lookup_object(f"#{pointer}", uri)[0]
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

    def convert(self, node: JsonObject | bool, base_uri: str, *, name: str | None = None) -> Schema:
        if node is True:
            return Schema(name=name)
        if node is False:
            return Schema(name=name, type="null")  # nothing validates; closest IR
        if not node:
            return Schema(name=name)

        ref: Any = node.get("$ref")
        if ref is None and isinstance(node.get("#ref"), str):  # misspelled key seen in vendor schemas
            ref = node["#ref"]
            log.warning("%s: '#ref' used instead of '$ref' (%s); accepting it", base_uri, ref)
        if isinstance(ref, str):
            try:
                target_name = self.name_for_ref(ref, base_uri)
            except RefError as exc:
                # dangling reference (seen in vendor schemas): keep loading, type as Any
                log.warning("%s: %s; treating as untyped", base_uri, exc)
                self.dangling_refs.append(ref)
                return Schema(name=name, description=text(node, "description"), extensions=extensions_of(node))
            if target_name is not None:
                extra: dict[str, Any] = {k: v for k, v in node.items() if k != "$ref"}
                return Schema(
                    ref=target_name,
                    name=name,
                    description=text(extra, "description"),
                    nullable=bool(extra.get("nullable") or extra.get("x-nullable")),
                    extensions=extensions_of(extra),
                )
            target, target_uri = self.resolver.lookup_object(ref, base_uri)
            return self.convert(target, target_uri, name=name)

        raw_type: Any = node.get("type")
        nullable = bool(node.get("nullable") or node.get("x-nullable"))
        type_: Any
        if isinstance(raw_type, list):
            type_list = as_list(cast(Any, raw_type))
            types = [t for t in type_list if t != "null"]
            nullable = nullable or len(types) != len(type_list)
            type_ = types[0] if len(types) == 1 else None
        else:
            type_ = raw_type
        fmt = node.get("format")
        if type_ == "file":  # Swagger 2.0 formData file parameter
            type_, fmt = "string", "binary"

        properties: dict[str, Schema] = {}
        for pname, pnode in obj(node, "properties").items():
            sub = self._schema_node(pnode)
            if sub is not None:
                properties[str(pname)] = self.convert(sub, base_uri)
        items_raw: Any = node.get("items")
        items_schema: Schema | None = None
        items_node = self._schema_node(items_raw)
        if items_node is not None:
            items_schema = self.convert(items_node, base_uri)
        elif isinstance(items_raw, list):  # tuple validation: not representable, keep Any
            items_schema = Schema()

        additional: Schema | bool | None = None
        ap: Any = node.get("additionalProperties")
        if isinstance(ap, bool):
            additional = ap
        elif (ap_obj := as_object(ap)) is not None:
            additional = self.convert(ap_obj, base_uri)

        enum: Any = node.get("enum")
        required: Any = node.get("required")
        disc: Any = node.get("discriminator")
        discriminator: Discriminator | None = None
        if isinstance(disc, str):
            discriminator = Discriminator(property_name=disc)
        elif (disc_obj := as_object(disc)) is not None and isinstance(disc_obj.get("propertyName"), str):
            mapping: dict[str, str] = {}
            for value, target in obj(disc_obj, "mapping").items():
                mapped = self.name_for_ref(target, base_uri) if isinstance(target, str) else None
                mapping[str(value)] = mapped if mapped is not None else str(target)
            discriminator = Discriminator(property_name=str(disc_obj["propertyName"]), mapping=mapping)

        example: Any = node.get("example")
        examples = as_list(node.get("examples"))
        if example is None and examples:
            example = examples[0]

        return Schema(
            name=name,
            title=text(node, "title"),
            description=text(node, "description"),
            type=type_ if isinstance(type_, str) else None,
            format=fmt if isinstance(fmt, str) else None,
            nullable=nullable,
            properties=properties,
            required=frozenset(str(r) for r in as_list(required)),
            items=items_schema,
            additional_properties=additional,
            enum=_enum_values(enum),
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
        out: list[Schema] = []
        for n in as_list(nodes):
            sub = self._schema_node(n)
            if sub is not None:
                out.append(self.convert(sub, base_uri))
        return tuple(out)

    @staticmethod
    def _schema_node(value: Any) -> JsonObject | bool | None:
        if isinstance(value, bool):
            return value
        return as_object(value)


__all__ = ["SchemaConverter", "extensions_of"]
