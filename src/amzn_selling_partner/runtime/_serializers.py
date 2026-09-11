"""Parameter serializers, built once per operation when a resource module is
imported (the generated ``path()`` / ``query()`` / ``header()`` literals).

Each factory returns a small closure specialised for one parameter (location,
style, explode, item kind) so the per-call path is one function call with no
branching on the spec. Query serializers return an already percent-encoded
``name=value[&name=value]`` fragment; path and header serializers return the
encoded value.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal, cast
from urllib.parse import quote

Encoder = Callable[[Any], str]
ParamKind = Literal["scalar", "array", "object"]

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


def query_serializer(
    name: str, kind: ParamKind = "scalar", *, style: str = "form", explode: bool = True, allow_reserved: bool = False
) -> Encoder:
    """Return ``f(value) -> "k=v&k=v"`` (percent-encoded) for a query parameter."""
    qname = quote(name, safe=_SAFE_QUERY)
    safe = "/:" if allow_reserved else _SAFE_QUERY
    if kind == "array":
        if style == "form" and explode:

            def encode_multi(value: Any) -> str:
                return "&".join(f"{qname}={quote(scalar(v), safe=safe)}" for v in _items(value))

            return encode_multi
        delim = "," if style == "form" else quote(_DELIMS.get(style, ","), safe="")

        def encode_joined(value: Any) -> str:
            return f"{qname}={delim.join(quote(scalar(v), safe=safe) for v in _items(value))}"

        return encode_joined
    if kind == "object":
        if style == "deepObject":

            def encode_deep(value: Any) -> str:
                mapping = _mapping(value, name)
                return "&".join(f"{qname}%5B{quote(str(k), safe='')}%5D={quote(scalar(v), safe=safe)}" for k, v in mapping.items())

            return encode_deep
        if explode:

            def encode_obj_exploded(value: Any) -> str:
                mapping = _mapping(value, name)
                return "&".join(f"{quote(str(k), safe='')}={quote(scalar(v), safe=safe)}" for k, v in mapping.items())

            return encode_obj_exploded

        def encode_obj(value: Any) -> str:
            mapping = _mapping(value, name)
            flat = ",".join(f"{quote(str(k), safe='')},{quote(scalar(v), safe=safe)}" for k, v in mapping.items())
            return f"{qname}={flat}"

        return encode_obj

    def encode_scalar(value: Any) -> str:
        return f"{qname}={quote(scalar(value), safe=safe)}"

    return encode_scalar


def path_serializer(
    name: str, kind: ParamKind = "scalar", *, style: str = "simple", explode: bool = False, allow_reserved: bool = False
) -> Encoder:
    """Return ``f(value) -> encoded segment`` for a path parameter."""
    safe = _SAFE_PATH_RESERVED if allow_reserved else _SAFE_PATH
    if style == "label":
        prefix, sep = ".", "." if explode else ","
    elif style == "matrix":
        prefix, sep = f";{name}=", f";{name}=" if explode else ","
    else:
        prefix, sep = "", ","

    if kind == "array":

        def encode_array(value: Any) -> str:
            return prefix + sep.join(quote(scalar(v), safe=safe) for v in _items(value))

        return encode_array
    if kind == "object":
        kv = "=" if explode else ","
        isep = sep if (explode or style != "simple") else ","

        def encode_object(value: Any) -> str:
            mapping = _mapping(value, name)
            body = isep.join(f"{quote(str(k), safe='')}{kv}{quote(scalar(v), safe=safe)}" for k, v in mapping.items())
            if style == "matrix" and explode:
                return ";" + body
            return prefix + body

        return encode_object

    def encode_scalar(value: Any) -> str:
        if value is None:
            raise TypeError(f"path parameter {name!r} must not be None")
        return prefix + quote(scalar(value), safe=safe)

    return encode_scalar


def header_serializer(
    name: str, kind: ParamKind = "scalar", *, style: str = "simple", explode: bool = False, allow_reserved: bool = False
) -> Encoder:
    del style, allow_reserved  # headers are always simple-style
    if kind == "array":

        def encode_array(value: Any) -> str:
            return ",".join(scalar(v) for v in _items(value))

        return encode_array
    if kind == "object":
        kv = "=" if explode else ","

        def encode_object(value: Any) -> str:
            mapping = _mapping(value, name)
            return ",".join(f"{k}{kv}{scalar(v)}" for k, v in mapping.items())

        return encode_object

    return scalar


__all__ = ["Encoder", "ParamKind", "header_serializer", "path_serializer", "query_serializer", "scalar"]
