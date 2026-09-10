"""JSON codecs. The default is pydantic-core (fast, bytes in / bytes out); the
stdlib implementation exists for tests and for environments that want to swap
in another encoder."""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from pydantic_core import from_json, to_json


@runtime_checkable
class JsonCodec(Protocol):
    def loads(self, data: bytes | bytearray | memoryview | str, /) -> Any: ...

    def dumps(self, obj: Any, /) -> bytes: ...


class PydanticJsonCodec:
    """``pydantic_core.from_json`` / ``to_json``."""

    __slots__ = ()

    def loads(self, data: bytes | bytearray | memoryview | str, /) -> Any:
        return from_json(data)

    def dumps(self, obj: Any, /) -> bytes:
        return to_json(obj)


class StdlibJsonCodec:
    """``json.loads`` / ``json.dumps`` from the standard library."""

    __slots__ = ()

    def loads(self, data: bytes | bytearray | memoryview | str, /) -> Any:
        if isinstance(data, memoryview):
            data = data.tobytes()
        return json.loads(data)

    def dumps(self, obj: Any, /) -> bytes:
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode()


DEFAULT_CODEC: JsonCodec = PydanticJsonCodec()
