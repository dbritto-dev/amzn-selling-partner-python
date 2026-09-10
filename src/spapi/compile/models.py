"""Schema -> pydantic v2 model compiler.

Design
------
* One ``ModelNamespace`` per document (API version). It is lazy: a named schema
  is turned into a class or type alias the first time it is requested, and
  ``build_all()`` forces everything (used by ``preload`` and the stub checker).
* Object schemas become classes created with ``create_model`` and the config
  ``defer_build=True, extra="allow", populate_by_name=True, frozen=True``; field
  aliases carry the spec's casing while attribute names are snake_case.
* Non-object named schemas (arrays, primitives, enums, unions) become type
  aliases stored in the same namespace.
* Recursion: dependencies are built depth-first. A back-edge to a schema that is
  still being built is emitted as a string forward reference; every class is
  registered in a real module (``spapi.models.<key>``) so pydantic resolves those
  references itself when it builds the schema on first use, or explicitly via
  ``model_rebuild()`` in ``build_all``.
* Memoisation: ``(document hash, schema name)`` -> type, process-wide.
* No validators, no computed fields, no descriptions on fields (they live in
  the IR and in the generated stubs).
"""

from __future__ import annotations

import datetime
import logging
import sys
import threading
import types
from collections.abc import Iterator
from typing import Annotated, Any, Literal, Optional, Union, cast

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, create_model

from ..spec.ir import Document, Schema
from .naming import class_name, field_name, pascal_case

log = logging.getLogger("spapi.compile.models")

MODEL_CONFIG = ConfigDict(
    defer_build=True,
    extra="allow",
    populate_by_name=True,
    frozen=True,
    val_json_bytes="base64",
    ser_json_bytes="base64",
)

# Config for TypeAdapters over non-model types (lists, unions, primitives).
ADAPTER_CONFIG = ConfigDict(
    populate_by_name=True,
    val_json_bytes="base64",
    ser_json_bytes="base64",
)

_FORMATS: dict[tuple[str, str], Any] = {
    ("string", "date-time"): datetime.datetime,
    ("string", "dateTime"): datetime.datetime,
    ("string", "date"): datetime.date,
    ("string", "byte"): bytes,
    ("string", "binary"): bytes,
}
_PRIMITIVES: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "null": type(None),
}

_MEMO: dict[tuple[str, str, str], Any] = {}
_MEMO_LOCK = threading.RLock()


def _module_for(key: str) -> types.ModuleType:
    name = f"spapi.models.{key}"
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name, f"Generated models for {key}")
        mod.__dict__.update(
            {
                "Optional": Optional,
                "Union": Union,
                "Literal": Literal,
                "Annotated": Annotated,
                "Any": Any,
                "datetime": datetime,
            }
        )
        sys.modules[name] = mod
    return mod


class ModelNamespace:
    """Lazy container of the models/type aliases of one document."""

    def __init__(
        self,
        document: Document,
        *,
        key: str | None = None,
        enum_mode: Literal["literal", "plain"] = "literal",
    ) -> None:
        self.document = document
        self.key = key or f"doc_{document.hash[:12]}"
        self.module = _module_for(self.key)
        self.enum_mode = enum_mode
        self._types: dict[str, Any] = {}
        self._building: set[str] = set()
        self._depth = 0
        self._forward: list[type[BaseModel]] = []
        self._adapters: dict[Any, TypeAdapter[Any]] = {}
        self._lock = threading.RLock()

    # -- public ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name not in self.document.schemas:
            raise AttributeError(name)
        return self.get(name)

    def __dir__(self) -> list[str]:
        return sorted(set(self.document.schemas) | set(super().__dir__()))

    def __contains__(self, name: str) -> bool:
        return name in self.document.schemas

    def __iter__(self) -> Iterator[str]:
        return iter(self.document.schemas)

    def get(self, name: str) -> Any:
        """Return the python type for the named schema, building it if needed."""
        t = self._types.get(name)
        if t is not None:
            return t
        with self._lock:
            t = self._types.get(name)
            if t is not None:
                return t
            memo_key = (self.document.hash, self.enum_mode, name)
            t = _MEMO.get(memo_key)
            if t is not None:
                self._types[name] = t
                setattr(self.module, class_name(name), t)
                return t
            self._depth += 1
            try:
                t = self._build_named(name)
            finally:
                self._depth -= 1
            if self._depth == 0:
                self._resolve_forward()
            return t

    def build_all(self) -> int:
        """Build every named schema and force model schemas; returns the count."""
        for name in list(self.document.schemas):
            self.get(name)
        self._resolve_forward(force=True)
        for t in self._types.values():
            if isinstance(t, type) and issubclass(t, BaseModel):
                t.model_rebuild()
        return len(self._types)

    def type_for(self, schema: Schema, *, name_hint: str = "") -> Any:
        """Python type annotation for an (inline or referenced) schema."""
        with self._lock:
            self._depth += 1
            try:
                t = self._annotation(schema, name_hint or "Inline")
            finally:
                self._depth -= 1
            if self._depth == 0:
                self._resolve_forward()
            return t

    def adapter(self, schema: Schema, *, name_hint: str = "") -> TypeAdapter[Any]:
        """A cached ``TypeAdapter`` for the schema's python type."""
        t = self.type_for(schema, name_hint=name_hint)
        return self.adapter_for_type(t)

    def adapter_for_type(self, t: Any) -> TypeAdapter[Any]:
        key = t if isinstance(t, type) else repr(t)
        ad = self._adapters.get(key)
        if ad is None:
            if isinstance(t, type) and issubclass(t, BaseModel):
                ad = TypeAdapter(t)
            else:
                ad = TypeAdapter(t, config=ADAPTER_CONFIG)
            self._adapters[key] = ad
        return ad

    @property
    def built(self) -> dict[str, Any]:
        return dict(self._types)

    # -- building ------------------------------------------------------------------

    def _build_named(self, name: str) -> Any:
        schema = self.document.schemas[name]
        self._building.add(name)
        try:
            t = self._annotation(schema, name, named=True)
        finally:
            self._building.discard(name)
        self._types[name] = t
        _MEMO[(self.document.hash, self.enum_mode, name)] = t
        setattr(self.module, class_name(name), t)
        return t

    def _resolve_forward(self, *, force: bool = False) -> None:
        # Models that carry string forward references get their schema built
        # by pydantic on first use, from ``self.module``'s namespace. Nothing to
        # do eagerly unless forced (build_all / tests).
        if force:
            for m in self._forward:
                m.model_rebuild(_types_namespace=dict(self.module.__dict__))
            self._forward.clear()

    def _ref_type(self, ref: str) -> Any:
        if ref in self._building:
            return class_name(ref)  # forward reference; resolved from the module
        return self.get(ref)

    def _annotation(self, schema: Schema, name: str, *, named: bool = False) -> Any:
        if schema.ref is not None:
            t = self._ref_type(schema.ref)
            return Optional[t] if schema.nullable else t  # noqa: UP045 - Optional accepts str refs

        t = self._concrete(schema, name, named=named)
        if schema.nullable:
            t = Optional[t]  # noqa: UP045
        return t

    def _concrete(self, schema: Schema, name: str, *, named: bool) -> Any:
        if schema.all_of:
            return self._all_of(schema, name)
        if schema.one_of or schema.any_of:
            return self._union(schema, name)
        if schema.has_const:
            return Literal[schema.const]
        if schema.enum is not None and self.enum_mode == "literal":
            values = tuple(v for v in schema.enum if v is not None)
            if values:
                t = Literal[values]  # type: ignore[valid-type]
                return Optional[t] if len(values) != len(schema.enum) else t  # noqa: UP045
        typ = schema.type
        if typ == "object" or (typ is None and (schema.properties or schema.additional_properties is not None)):
            if schema.properties:
                return self._object_model(schema, name)
            ap = schema.additional_properties
            if isinstance(ap, Schema):
                return dict[str, self._annotation(ap, name + "Value")]  # type: ignore[misc]
            return dict[str, Any]
        if typ == "array":
            item_t = self._annotation(schema.items, name + "Item") if schema.items is not None else Any
            return list[item_t]  # type: ignore[valid-type]
        if typ is not None:
            fmt_t = _FORMATS.get((typ, schema.format or ""))
            if fmt_t is not None:
                return fmt_t
            return _PRIMITIVES.get(typ, Any)
        return Any

    def _all_of(self, schema: Schema, name: str) -> Any:
        props: dict[str, Schema] = {}
        required: set[str] = set()
        parts = [self.document.resolve(p) for p in schema.all_of]
        non_object = [p for p in parts if not (p.properties or p.type == "object" or p.all_of)]
        if non_object and len(parts) == 1:
            return self._annotation(schema.all_of[0], name)
        for part in parts:
            merged = self._merged_object(part)
            props.update(merged.properties)
            required |= set(merged.required)
        props.update(schema.properties)
        required |= set(schema.required)
        merged_schema = Schema(
            name=name,
            type="object",
            properties=props,
            required=frozenset(required),
            description=schema.description,
            extensions=schema.extensions,
        )
        return self._object_model(merged_schema, name)

    def _merged_object(self, schema: Schema) -> Schema:
        """Flatten nested allOf chains into one object schema (properties + required)."""
        if not schema.all_of:
            return schema
        props: dict[str, Schema] = {}
        required: set[str] = set()
        for part in schema.all_of:
            m = self._merged_object(self.document.resolve(part))
            props.update(m.properties)
            required |= set(m.required)
        props.update(schema.properties)
        required |= set(schema.required)
        return Schema(type="object", properties=props, required=frozenset(required))

    def _union(self, schema: Schema, name: str) -> Any:
        variants = schema.one_of or schema.any_of
        types_: list[Any] = []
        for i, v in enumerate(variants):
            resolved = self.document.resolve(v)
            if resolved.type == "null" and not resolved.properties:
                types_.append(type(None))
            else:
                types_.append(self._annotation(v, f"{name}Variant{i + 1}"))
        if len(types_) == 1:
            return types_[0]
        union = Union[tuple(types_)]  # type: ignore[valid-type]  # noqa: UP007
        disc = schema.discriminator
        if disc is not None and all(isinstance(t, (type, str)) for t in types_ if t is not type(None)):
            return Annotated[union, Field(discriminator=field_name(disc.property_name))]
        return union

    def _object_model(self, schema: Schema, name: str) -> type[BaseModel]:
        cls_name = class_name(name if schema.name is None or schema.name == name else schema.name)
        fields: dict[str, Any] = {}
        used: set[str] = set()
        has_forward = False
        for wire, prop in schema.properties.items():
            py = field_name(wire)
            if py in used:
                n = 2
                while f"{py}_{n}" in used:
                    n += 1
                py = f"{py}_{n}"
            used.add(py)
            hint = pascal_case(wire)
            ann = self._annotation(prop, f"{cls_name}{hint}")
            if _has_forward_ref(ann):
                has_forward = True
            if wire in schema.required:
                info = Field(alias=wire) if wire != py else Field()
            else:
                ann = Optional[ann]  # noqa: UP045
                info = Field(default=None, alias=wire) if wire != py else Field(default=None)
            fields[py] = (ann, info)
        model = create_model(  # type: ignore[call-overload]
            cls_name,
            __config__=MODEL_CONFIG,
            __module__=self.module.__name__,
            __doc__=schema.description or None,
            **fields,
        )
        model = cast(type[BaseModel], model)
        if not schema.name or schema.name != name:
            # inline object: expose it in the module too so forward refs work
            setattr(self.module, cls_name, model)
        if has_forward:
            self._forward.append(model)
        return model


def _has_forward_ref(ann: Any) -> bool:
    if isinstance(ann, str):
        return True
    args = getattr(ann, "__args__", None)
    if args:
        return any(_has_forward_ref(a) for a in args)
    return False


def build_models(
    document: Document, *, key: str | None = None, enum_mode: Literal["literal", "plain"] = "literal"
) -> ModelNamespace:
    return ModelNamespace(document, key=key, enum_mode=enum_mode)


def clear_memo() -> None:
    """Drop the process-wide model cache (tests)."""
    with _MEMO_LOCK:
        _MEMO.clear()


__all__ = ["ADAPTER_CONFIG", "MODEL_CONFIG", "ModelNamespace", "build_models", "clear_memo"]
