"""Render IR schemas as Python type expressions (strings).

Used for the ``inspect.Signature`` annotations of compiled operations (so that
signatures never force model creation) and by the stub generator. The naming
mirrors ``compile/models.py``: named schemas keep their class name, inline
objects are ``<Parent><Field>``, array items ``<Parent>Item``.
"""

from __future__ import annotations

from collections.abc import Callable

from ..spec.ir import Document, Schema
from .naming import class_name

_PRIMITIVES = {"string": "str", "integer": "int", "number": "float", "boolean": "bool", "null": "None"}
_FORMATS = {
    ("string", "date-time"): "datetime.datetime",
    ("string", "dateTime"): "datetime.datetime",
    ("string", "date"): "datetime.date",
    ("string", "byte"): "bytes",
    ("string", "binary"): "bytes",
}


def type_expr(
    document: Document, schema: Schema, hint: str = "Inline", *, model_prefix: str = "", literal_enums: bool = True, dict_suffix: str = ""
) -> str:
    """Type expression for ``schema``. ``model_prefix`` prefixes class names
    (e.g. ``"models."``); ``dict_suffix`` renames model classes (raw-mode
    ``TypedDict`` variants, e.g. ``"Dict"``)."""

    def render(s: Schema, name: str) -> str:
        if s.ref is not None:
            base = f"{model_prefix}{class_name(s.ref)}{dict_suffix if _is_object(document, document.schemas[s.ref]) else ''}"
            return f"{base} | None" if s.nullable else base
        expr = _concrete(document, s, name, render, literal_enums, model_prefix, dict_suffix)
        return f"{expr} | None" if s.nullable and expr != "None" else expr

    return render(schema, hint)


def _is_object(document: Document, schema: Schema) -> bool:
    s = document.resolve(schema)
    if s.all_of:
        return True
    return bool(s.properties) or (s.type == "object" and s.additional_properties is None and not s.properties and False)


def _concrete(
    document: Document, s: Schema, name: str, render: Callable[[Schema, str], str], literal_enums: bool, model_prefix: str, dict_suffix: str
) -> str:
    if s.all_of:
        return f"{model_prefix}{class_name(name)}{dict_suffix}"
    if s.one_of or s.any_of:
        parts: list[str] = []
        for i, v in enumerate(s.one_of or s.any_of):
            r = document.resolve(v)
            parts.append("None" if r.type == "null" and not r.properties else render(v, f"{name}Variant{i + 1}"))
        return " | ".join(dict.fromkeys(parts))
    if s.has_const:
        return f"Literal[{s.const!r}]"
    if s.enum is not None and literal_enums:
        values = [v for v in s.enum if v is not None]
        if values:
            lit = "Literal[" + ", ".join(repr(v) for v in values) + "]"
            return f"{lit} | None" if len(values) != len(s.enum) else lit
    typ = s.type
    if typ == "object" or (typ is None and (s.properties or s.additional_properties is not None)):
        if s.properties:
            return f"{model_prefix}{class_name(name)}{dict_suffix}"
        if isinstance(s.additional_properties, Schema):
            return f"dict[str, {render(s.additional_properties, name + 'Value')}]"
        return "dict[str, Any]"
    if typ == "array":
        return f"list[{render(s.items, name + 'Item') if s.items is not None else 'Any'}]"
    if typ is not None:
        return _FORMATS.get((typ, s.format or ""), _PRIMITIVES.get(typ, "Any"))
    return "Any"


__all__ = ["type_expr"]
