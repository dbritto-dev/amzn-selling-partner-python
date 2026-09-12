"""Naming rules shared with ``codegen/src/python/naming.ts``."""

from __future__ import annotations

import re


def snake_case(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z_]+", "_", name)
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"_+", "_", s).strip("_").lower()
    return s or "field"


def api_version_of(module: str) -> tuple[str, str] | None:
    """``orders_v0`` -> ``("orders", "v0")`` (the resource module of an API version)."""
    m = re.match(r"^(.+?)_(v\d.*)$", module)
    return (m.group(1), m.group(2)) if m else None


__all__ = ["api_version_of", "snake_case"]
