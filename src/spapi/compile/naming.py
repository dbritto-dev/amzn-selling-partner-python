"""Identifier helpers shared by the compiler and stub generator."""

from __future__ import annotations

import keyword
import re

_CAMEL_1 = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_2 = re.compile(r"([a-z0-9])([A-Z])")
_INVALID = re.compile(r"[^0-9a-zA-Z_]+")

# Names that must not be used as pydantic field names.
_MODEL_RESERVED = frozenset(
    {
        "schema",
        "copy",
        "json",
        "dict",
        "validate",
        "construct",
        "fields",
        "parse_obj",
        "parse_raw",
        "parse_file",
        "from_orm",
        "update_forward_refs",
        "schema_json",
    }
)
# Names that must not be used as class names inside a models module, because
# the generated forward references are evaluated in that namespace.
_MODULE_RESERVED = frozenset(
    {
        "list",
        "dict",
        "str",
        "int",
        "float",
        "bool",
        "bytes",
        "None",
        "Any",
        "Optional",
        "Union",
        "Literal",
        "Annotated",
        "datetime",
        "date",
        "Field",
        "BaseModel",
    }
)


def snake_case(name: str) -> str:
    """``AmazonOrderId`` -> ``amazon_order_id``; ``x-amzn-foo`` -> ``x_amzn_foo``."""
    s = _INVALID.sub("_", name)
    s = _CAMEL_1.sub(r"\1_\2", s)
    s = _CAMEL_2.sub(r"\1_\2", s)
    s = re.sub(r"_+", "_", s).strip("_").lower()
    return s or "field"


def pascal_case(name: str) -> str:
    parts = [p for p in _INVALID.sub("_", name).split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Model"


def identifier(name: str) -> str:
    """Make ``name`` a valid, non-keyword python identifier (keeps case)."""
    s = _INVALID.sub("_", name)
    if not s or s[0].isdigit():
        s = "_" + s
    if keyword.iskeyword(s):
        s += "_"
    return s


def field_name(wire_name: str) -> str:
    """Python attribute name for a spec property name."""
    s = snake_case(wire_name)
    if s[0].isdigit():
        s = "n" + s
    if s.startswith("_"):
        s = "x" + s
    if keyword.iskeyword(s) or s in _MODEL_RESERVED or s.startswith("model_"):
        s += "_"
    return s


def param_name(wire_name: str) -> str:
    """Python keyword name for an operation parameter."""
    s = snake_case(wire_name)
    if s[0].isdigit():
        s = "p" + s
    if keyword.iskeyword(s) or s in ("self", "raw", "request_options", "body"):
        s += "_"
    return s


def method_name(operation_id: str) -> str:
    s = snake_case(operation_id)
    if keyword.iskeyword(s):
        s += "_"
    return s


def class_name(schema_name: str) -> str:
    s = identifier(schema_name)
    if s in _MODULE_RESERVED:
        s += "_"
    return s


__all__ = [
    "class_name",
    "field_name",
    "identifier",
    "method_name",
    "param_name",
    "pascal_case",
    "snake_case",
]
