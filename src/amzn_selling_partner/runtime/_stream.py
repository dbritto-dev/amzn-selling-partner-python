"""Streaming response bodies: chunked bytes and Server-Sent Events.

Both classes wrap an ``httpx2.Response`` opened in streaming mode and parse
frames at the bytes level in 64 KiB reads.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Any

import httpx2

if TYPE_CHECKING:
    from typing_extensions import Self

CHUNK_SIZE = 64 * 1024


@dataclass(slots=True, frozen=True)
class ServerSentEvent:
    data: str
    event: str | None = None
    id: str | None = None
    retry: int | None = None

    def json(self) -> Any:
        from pydantic_core import from_json

        return from_json(self.data)


class _SSEParser:
    """Incremental SSE parser working on bytes (RFC: whatwg EventSource)."""

    __slots__ = ("_buf",)

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> list[ServerSentEvent]:
        self._buf += chunk
        events: list[ServerSentEvent] = []
        while True:
            # a frame ends at a blank line: \n\n, \r\n\r\n or \r\r
            idx, sep_len = self._find_frame_end()
            if idx < 0:
                break
            frame = bytes(self._buf[:idx])
            del self._buf[: idx + sep_len]
            ev = self._parse_frame(frame)
            if ev is not None:
                events.append(ev)
        return events

    def flush(self) -> ServerSentEvent | None:
        if not self._buf:
            return None
        frame = bytes(self._buf)
        self._buf.clear()
        return self._parse_frame(frame)

    def _find_frame_end(self) -> tuple[int, int]:
        best = -1
        best_len = 0
        for sep in (b"\r\n\r\n", b"\n\n", b"\r\r"):
            i = self._buf.find(sep)
            if i >= 0 and (best < 0 or i < best):
                best, best_len = i, len(sep)
        return best, best_len

    @staticmethod
    def _parse_frame(frame: bytes) -> ServerSentEvent | None:
        data: list[str] = []
        event: str | None = None
        id_: str | None = None
        retry: int | None = None
        for raw_line in frame.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n"):
            if not raw_line or raw_line.startswith(b":"):
                continue
            name, sep, value = raw_line.partition(b":")
            if sep and value.startswith(b" "):
                value = value[1:]
            field_ = name.decode("utf-8", "replace")
            text = value.decode("utf-8", "replace")
            if field_ == "data":
                data.append(text)
            elif field_ == "event":
                event = text
            elif field_ == "id":
                id_ = text
            elif field_ == "retry":
                try:
                    retry = int(text)
                except ValueError:
                    pass
        if not data and event is None and id_ is None:
            return None
        return ServerSentEvent(data="\n".join(data), event=event, id=id_, retry=retry)


class Stream:
    """Synchronous streaming body. Iterate bytes with ``iter_bytes`` or SSE
    frames with ``iter_events``; ``close`` (or the context manager) releases
    the connection back to the pool."""

    __slots__ = ("response",)

    def __init__(self, response: httpx2.Response) -> None:
        self.response = response

    def iter_bytes(self, chunk_size: int = CHUNK_SIZE) -> Iterator[bytes]:
        return self.response.iter_bytes(chunk_size)

    def iter_lines(self) -> Iterator[str]:
        return self.response.iter_lines()

    def iter_events(self) -> Iterator[ServerSentEvent]:
        parser = _SSEParser()
        for chunk in self.response.iter_bytes(CHUNK_SIZE):
            yield from parser.feed(chunk)
        last = parser.flush()
        if last is not None:
            yield last

    def __iter__(self) -> Iterator[bytes]:
        return self.iter_bytes()

    def read(self) -> bytes:
        return self.response.read()

    def close(self) -> None:
        self.response.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()


class AsyncStream:
    __slots__ = ("response",)

    def __init__(self, response: httpx2.Response) -> None:
        self.response = response

    def iter_bytes(self, chunk_size: int = CHUNK_SIZE) -> AsyncIterator[bytes]:
        return self.response.aiter_bytes(chunk_size)

    def iter_lines(self) -> AsyncIterator[str]:
        return self.response.aiter_lines()

    async def iter_events(self) -> AsyncIterator[ServerSentEvent]:
        parser = _SSEParser()
        async for chunk in self.response.aiter_bytes(CHUNK_SIZE):
            for ev in parser.feed(chunk):
                yield ev
        last = parser.flush()
        if last is not None:
            yield last

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self.iter_bytes()

    async def read(self) -> bytes:
        return await self.response.aread()

    async def aclose(self) -> None:
        await self.response.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        await self.aclose()


__all__ = ["CHUNK_SIZE", "AsyncStream", "ServerSentEvent", "Stream"]
