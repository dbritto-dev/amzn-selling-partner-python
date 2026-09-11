"""Parameter serializers built once per operation at compile time.

Each factory returns a small closure specialised for one parameter (location,
style, explode, item type) so the per-call path is one function call with no
branching on the spec. Query serializers return an already percent-encoded
``name=value[&name=value]`` fragment; path and header serializers return the
encoded value.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast
from urllib.parse import quote

from ..spec.ir import Parameter, Schema

Encoder = Callable[[Any], str]

_SAFE_QUERY = ""  # encode everything but unreserved characters
_SAFE_PATH = ""
_SAFE_PATH_RESERVED = "/"


def scalar(value: Any) -> str:
    """String form of a scalar parameter value (bool/datetime aware)."""
    if isinstance(value, str):
        return value
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            return value.isoformat(timespec="milliseconds") + "Z"
        s = value.isoformat(timespec="milliseconds")
        return s[:-6] + "Z" if s.endswith("+00:00") else s
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _items(value: Any) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return [value]
    return list(cast(Sequence[Any], value))


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"parameter {name!r} expects a mapping")
    return cast(Mapping[str, Any], value)


_DELIMS = {"form": ",", "spaceDelimited": " ", "pipeDelimited": "|", "tabDelimited": "\t"}


def query_serializer(param: Parameter, resolve: Callable[[Schema], Schema]) -> Encoder:
    """Return ``f(value) -> "k=v&k=v"`` (percent-encoded) for a query parameter."""
    name = quote(param.name, safe=_SAFE_QUERY)
    schema = resolve(param.schema)
    safe = "/:" if param.allow_reserved else _SAFE_QUERY
    style = param.style
    if schema.type == "array":
        if style == "form" and param.explode:

            def encode_multi(value: Any) -> str:
                return "&".join(f"{name}={quote(scalar(v), safe=safe)}" for v in _items(value))

            return encode_multi
        delim = "," if style == "form" else quote(_DELIMS.get(style, ","), safe="")

        def encode_joined(value: Any) -> str:
            return f"{name}={delim.join(quote(scalar(v), safe=safe) for v in _items(value))}"

        return encode_joined
    if schema.type == "object" or (schema.type is None and schema.properties):
        if style == "deepObject":

            def encode_deep(value: Any) -> str:
                mapping = _mapping(value, param.name)
                return "&".join(f"{name}%5B{quote(str(k), safe='')}%5D={quote(scalar(v), safe=safe)}" for k, v in mapping.items())

            return encode_deep
        if param.explode:

            def encode_obj_exploded(value: Any) -> str:
                mapping = _mapping(value, param.name)
                return "&".join(f"{quote(str(k), safe='')}={quote(scalar(v), safe=safe)}" for k, v in mapping.items())

            return encode_obj_exploded

        def encode_obj(value: Any) -> str:
            mapping = _mapping(value, param.name)
            flat = ",".join(f"{quote(str(k), safe='')},{quote(scalar(v), safe=safe)}" for k, v in mapping.items())
            return f"{name}={flat}"

        return encode_obj

    def encode_scalar(value: Any) -> str:
        return f"{name}={quote(scalar(value), safe=safe)}"

    return encode_scalar


def path_serializer(param: Parameter, resolve: Callable[[Schema], Schema]) -> Encoder:
    """Return ``f(value) -> encoded segment`` for a path parameter."""
    schema = resolve(param.schema)
    safe = _SAFE_PATH_RESERVED if param.allow_reserved or param.extensions.get("x-amazon-spds-greedy-path-parameter") else _SAFE_PATH
    style = param.style
    is_array = schema.type == "array"
    is_object = schema.type == "object" or (schema.type is None and bool(schema.properties))

    if style == "label":
        prefix, sep = ".", "." if param.explode else ","
    elif style == "matrix":
        prefix, sep = f";{param.name}=", f";{param.name}=" if param.explode else ","
    else:
        prefix, sep = "", ","

    if is_array:

        def encode_array(value: Any) -> str:
            return prefix + sep.join(quote(scalar(v), safe=safe) for v in _items(value))

        return encode_array
    if is_object:
        kv = "=" if param.explode else ","
        isep = sep if (param.explode or style != "simple") else ","

        def encode_object(value: Any) -> str:
            mapping = _mapping(value, param.name)
            body = isep.join(f"{quote(str(k), safe='')}{kv}{quote(scalar(v), safe=safe)}" for k, v in mapping.items())
            return (
                (prefix if style != "matrix" or param.explode else f";{param.name}=") + body
                if style != "matrix" or not param.explode
                else ";" + body
            )

        return encode_object

    def encode_scalar(value: Any) -> str:
        if value is None:
            raise TypeError(f"path parameter {param.name!r} must not be None")
        return prefix + quote(scalar(value), safe=safe)

    return encode_scalar


def header_serializer(param: Parameter, resolve: Callable[[Schema], Schema]) -> Encoder:
    schema = resolve(param.schema)
    if schema.type == "array":

        def encode_array(value: Any) -> str:
            return ",".join(scalar(v) for v in _items(value))

        return encode_array
    if schema.type == "object" or (schema.type is None and schema.properties):
        kv = "=" if param.explode else ","

        def encode_object(value: Any) -> str:
            mapping = _mapping(value, param.name)
            return ",".join(f"{k}{kv}{scalar(v)}" for k, v in mapping.items())

        return encode_object

    return scalar


__all__ = ["Encoder", "header_serializer", "path_serializer", "query_serializer", "scalar"]
