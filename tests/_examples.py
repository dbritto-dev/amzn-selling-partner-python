"""Minimal example values derived from raw (Swagger 2.0 / OpenAPI 3) schemas.

Used by the sandbox runner (``tests/sandbox.py``) for operations that ship no
example.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

_FORMAT_EXAMPLES = {
    "date-time": "2020-01-01T00:00:00Z",
    "dateTime": "2020-01-01T00:00:00Z",
    "date": "2020-01-01",
    "byte": "aGVsbG8=",
    "binary": "aGVsbG8=",
    "email": "a@example.com",
    "uri": "https://example.com/x",
    "uuid": "123e4567-e89b-12d3-a456-426614174000",
}

Schema = Mapping[str, Any]


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, Mapping) else {}


def resolve(document: Mapping[str, Any], schema: Schema) -> dict[str, Any]:
    """Follow ``$ref`` (``#/definitions/X`` or ``#/components/schemas/X``) within ``document``."""
    seen = 0
    s = _obj(schema)
    while isinstance(s.get("$ref"), str) and seen < 32:
        seen += 1
        node: Any = document
        for part in str(s["$ref"]).lstrip("#/").split("/"):
            node = _obj(node).get(part.replace("~1", "/").replace("~0", "~"))
        merged = dict(_obj(node))
        merged.update({k: v for k, v in s.items() if k != "$ref"})
        s = merged
    return s


def example_from_schema(document: Mapping[str, Any], schema: Schema, *, depth: int = 0, all_fields: bool = False) -> Any:
    """Return a JSON-compatible value that validates against ``schema``.

    Only required properties are emitted unless ``all_fields`` is set; recursion
    is cut at depth 6 by returning the emptiest valid value.
    """
    s = resolve(document, schema)
    if s.get("example") is not None and depth > 0:
        return s["example"]
    if "const" in s:
        return s["const"]
    enum = s.get("enum")
    if isinstance(enum, list) and enum:
        return next((v for v in cast(list[Any], enum) if v is not None), None)
    props = _obj(s.get("properties"))
    required: set[Any] = set(cast(list[Any], s["required"])) if isinstance(s.get("required"), list) else set()
    if isinstance(s.get("allOf"), list):
        out: dict[str, Any] = {}
        for part in cast(list[Any], s["allOf"]):
            v = example_from_schema(document, _obj(part), depth=depth + 1, all_fields=all_fields)
            if isinstance(v, dict):
                out.update(cast(dict[str, Any], v))
        for name, prop in props.items():
            if all_fields or name in required:
                out[name] = example_from_schema(document, _obj(prop), depth=depth + 1, all_fields=all_fields)
        return out
    variants_raw = s.get("oneOf") or s.get("anyOf")
    if isinstance(variants_raw, list):
        variants = [_obj(v) for v in cast(list[Any], variants_raw) if resolve(document, _obj(v)).get("type") != "null"]
        return example_from_schema(document, variants[0], depth=depth + 1, all_fields=all_fields) if variants else None
    typ = s.get("type")
    if isinstance(typ, list):
        typ = next((t for t in cast(list[Any], typ) if t != "null"), None)
    if depth > 6:
        all_fields = False  # stop expanding optional (possibly recursive) fields
    if typ == "object" or (typ is None and props):
        if depth > 12:
            return {}
        out = {}
        for name, prop in props.items():
            if all_fields or name in required:
                out[name] = example_from_schema(document, _obj(prop), depth=depth + 1, all_fields=all_fields)
        ap = s.get("additionalProperties")
        if not props and isinstance(ap, Mapping):
            out["key"] = example_from_schema(document, _obj(ap), depth=depth + 1, all_fields=all_fields)
        return out
    if typ == "array":
        items = s.get("items")
        if depth > 6 or not isinstance(items, Mapping):
            return []
        return [example_from_schema(document, _obj(items), depth=depth + 1, all_fields=all_fields)]
    if typ == "string":
        return _FORMAT_EXAMPLES.get(str(s.get("format") or ""), "example")
    if typ == "integer":
        return 1
    if typ == "number":
        return 1.5
    if typ == "boolean":
        return True
    if typ == "null":
        return None
    return {}


__all__ = ["example_from_schema", "resolve"]
