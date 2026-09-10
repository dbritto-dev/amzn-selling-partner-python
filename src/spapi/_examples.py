"""Minimal example values derived from IR schemas.

Used by the sandbox/mock test runner for operations that ship no example, and
by the test-suite to synthesise request arguments and response bodies.
"""

from __future__ import annotations

from typing import Any

from .spec.ir import Document, Schema

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


def example_from_schema(document: Document, schema: Schema, *, depth: int = 0, all_fields: bool = False) -> Any:
    """Return a JSON-compatible value that validates against ``schema``.

    Only required properties are emitted unless ``all_fields`` is set; recursion
    is cut at depth 6 by returning the emptiest valid value.
    """
    s = document.resolve(schema)
    if s.example is not None and depth > 0:
        return s.example
    if s.has_const:
        return s.const
    if s.enum:
        return next((v for v in s.enum if v is not None), None)
    if s.all_of:
        out: dict[str, Any] = {}
        for part in s.all_of:
            v = example_from_schema(document, part, depth=depth + 1, all_fields=all_fields)
            if isinstance(v, dict):
                out.update(v)
        for name, prop in s.properties.items():
            if all_fields or name in s.required:
                out[name] = example_from_schema(document, prop, depth=depth + 1, all_fields=all_fields)
        return out
    if s.one_of or s.any_of:
        variants = [v for v in (s.one_of or s.any_of) if document.resolve(v).type != "null"]
        return example_from_schema(document, variants[0], depth=depth + 1, all_fields=all_fields) if variants else None
    typ = s.type
    if depth > 6:
        all_fields = False  # stop expanding optional (possibly recursive) fields
    if typ == "object" or (typ is None and s.properties):
        if depth > 12:
            return {}
        out = {}
        for name, prop in s.properties.items():
            if all_fields or name in s.required:
                out[name] = example_from_schema(document, prop, depth=depth + 1, all_fields=all_fields)
        if not s.properties and isinstance(s.additional_properties, Schema):
            out["key"] = example_from_schema(document, s.additional_properties, depth=depth + 1, all_fields=all_fields)
        return out
    if typ == "array":
        if depth > 6 or s.items is None:
            return []
        return [example_from_schema(document, s.items, depth=depth + 1, all_fields=all_fields)]
    if typ == "string":
        return _FORMAT_EXAMPLES.get(s.format or "", "example")
    if typ == "integer":
        return 1
    if typ == "number":
        return 1.5
    if typ == "boolean":
        return True
    if typ == "null":
        return None
    return {}


__all__ = ["example_from_schema"]
