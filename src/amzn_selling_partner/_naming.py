"""Python naming rules, mirroring ``codegen/src/python/naming.ts`` (used by the
sandbox runner and the compatibility wrappers to map wire names to the
generated keyword arguments)."""

from __future__ import annotations

import keyword
import re

_KEYWORDS = set(keyword.kwlist) | {"match", "case", "type"}


def snake_case(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z_]+", "_", name)
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"_+", "_", s).strip("_").lower()
    return s or "field"


def pascal_case(name: str) -> str:
    parts = [p for p in re.sub(r"[^0-9a-zA-Z_]+", "_", name).split("_") if p]
    return "".join(p[0].upper() + p[1:] for p in parts) or "Model"


def param_name(wire_name: str) -> str:
    """Keyword argument name of an operation parameter."""
    s = snake_case(wire_name)
    if s[:1].isdigit():
        s = "p" + s
    if s in _KEYWORDS or s in {"self", "request_options", "body", "params", "headers"}:
        s += "_"
    return s


def field_name(wire_name: str) -> str:
    """Attribute name of a model field."""
    s = snake_case(wire_name)
    if s[:1].isdigit():
        s = "n" + s
    if s.startswith("_"):
        s = "x" + s
    reserved = {
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
    if s in _KEYWORDS or s in reserved or s.startswith("model_"):
        s += "_"
    return s


def api_version_of(module: str) -> tuple[str, str] | None:
    """``orders_v0`` -> ``("orders", "v0")`` (the resource module of an API version)."""
    m = re.match(r"^(.+?)_(v\d.*)$", module)
    return (m.group(1), m.group(2)) if m else None


__all__ = ["api_version_of", "field_name", "param_name", "pascal_case", "snake_case"]
