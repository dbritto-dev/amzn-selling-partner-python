"""Typed helpers for walking decoded JSON documents (keeps pyright strict quiet
without sprinkling casts through the normalisers)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

type JsonObject = Mapping[str, Any]


def as_object(value: object) -> JsonObject | None:
    return cast(JsonObject, value) if isinstance(value, Mapping) else None


def as_list(value: object) -> list[Any]:
    return cast(list[Any], value) if isinstance(value, list) else []


def obj(node: JsonObject, key: str) -> JsonObject:
    """``node[key]`` as an object, or ``{}``."""
    return as_object(node.get(key)) or {}


def objects(node: JsonObject, key: str) -> list[tuple[str, JsonObject]]:
    """``(name, object)`` pairs of a mapping-valued key, skipping non-objects."""
    out: list[tuple[str, JsonObject]] = []
    for name, value in obj(node, key).items():
        o = as_object(value)
        if o is not None:
            out.append((str(name), o))
    return out


def text(node: JsonObject, key: str) -> str | None:
    value = node.get(key)
    return value if isinstance(value, str) else None


def strings(node: JsonObject, key: str) -> tuple[str, ...]:
    return tuple(str(v) for v in as_list(node.get(key)))


__all__ = ["JsonObject", "as_list", "as_object", "obj", "objects", "strings", "text"]
