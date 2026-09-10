"""Default transports and connection options.

* Sync: ``httpx2.HTTPTransport``.
* Async: ``httpx_aiohttp.AiohttpTransport`` when the ``aiohttp`` extra is
  installed, else ``httpx2.AsyncHTTPTransport``.

``httpx_aiohttp`` is written against the ``httpx`` module. If the application
called ``httpx2.alias_httpx()`` at start-up the two are the same object and the
transport is used directly; otherwise a small bridge converts requests and
responses between the two packages (same wire behaviour, one extra object per
request).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx2

log = logging.getLogger("spapi.runtime.transports")

DEFAULT_LIMITS = httpx2.Limits(max_connections=100, max_keepalive_connections=50)
DEFAULT_TIMEOUT = httpx2.Timeout(30.0, connect=10.0)


def make_limits(max_connections: int = 100, max_keepalive: int = 50, keepalive_expiry: float | None = 5.0) -> httpx2.Limits:
    return httpx2.Limits(
        max_connections=max_connections,
        max_keepalive_connections=max_keepalive,
        keepalive_expiry=keepalive_expiry,
    )


def sync_transport(*, limits: httpx2.Limits = DEFAULT_LIMITS, verify: Any = True, http2: bool = False) -> httpx2.BaseTransport:
    return httpx2.HTTPTransport(limits=limits, verify=verify, http2=http2)


def aiohttp_available() -> bool:
    try:
        import httpx_aiohttp  # noqa: F401
    except ImportError:
        return False
    return True


def async_transport(
    *,
    limits: httpx2.Limits = DEFAULT_LIMITS,
    verify: Any = True,
    http2: bool = False,
    prefer_aiohttp: bool = True,
) -> httpx2.AsyncBaseTransport:
    if prefer_aiohttp:
        try:
            import httpx_aiohttp
            import httpx_aiohttp.transport as _hat
        except ImportError:
            pass
        else:
            inner = httpx_aiohttp.AiohttpTransport(limits=limits, verify=verify)
            if getattr(_hat, "httpx", None) is httpx2:  # alias_httpx() was called
                return inner  # type: ignore[return-value]
            return _HttpxBridgeTransport(inner, _hat.httpx)
    return httpx2.AsyncHTTPTransport(limits=limits, verify=verify, http2=http2)


class _BridgedStream(httpx2.AsyncByteStream):
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._inner:
            yield chunk

    async def aclose(self) -> None:
        aclose = getattr(self._inner, "aclose", None)
        if aclose is not None:
            await aclose()


class _HttpxBridgeTransport(httpx2.AsyncBaseTransport):
    """Adapts a transport written for ``httpx`` to ``httpx2``'s interface."""

    def __init__(self, inner: Any, httpx_mod: Any) -> None:
        self._inner = inner
        self._httpx = httpx_mod

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        hx = self._httpx
        old_req = hx.Request(
            request.method,
            str(request.url),
            headers=request.headers.raw,
            stream=_BridgedStream(request.stream),  # type: ignore[arg-type]
            extensions=dict(request.extensions),
        )
        old_resp = await self._inner.handle_async_request(old_req)
        return httpx2.Response(
            status_code=old_resp.status_code,
            headers=old_resp.headers.raw,
            stream=_BridgedStream(old_resp.stream),
            extensions=dict(old_resp.extensions),
        )

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def __aenter__(self) -> _HttpxBridgeTransport:
        await self._inner.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._inner.__aexit__(*args)


__all__ = [
    "DEFAULT_LIMITS",
    "DEFAULT_TIMEOUT",
    "aiohttp_available",
    "async_transport",
    "make_limits",
    "sync_transport",
]
