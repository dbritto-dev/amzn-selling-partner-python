"""Pluggable authentication hooks.

A hook is called once per attempt with the compiled operation and the fully
built ``httpx2.Request``; it returns the headers to add (or ``None``). Keeping
the hook outside the request builder means auth never touches the precomputed
header tuples, and the sync/async variants differ only in ``await``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import httpx2

    from ..compile.operations import CompiledOp


@runtime_checkable
class AuthHook(Protocol):
    def before_request(self, op: CompiledOp, request: httpx2.Request) -> Mapping[str, str] | None: ...


@runtime_checkable
class AsyncAuthHook(Protocol):
    def before_request(
        self, op: CompiledOp, request: httpx2.Request
    ) -> Awaitable[Mapping[str, str] | None]: ...


class NoAuth:
    """Hook that adds nothing; usable for both sync and async clients."""

    __slots__ = ()

    def before_request(self, op: CompiledOp, request: httpx2.Request) -> None:
        return None


class AsyncNoAuth:
    __slots__ = ()

    async def before_request(self, op: CompiledOp, request: httpx2.Request) -> None:
        return None


class StaticHeaderAuth:
    """Always send the same headers (e.g. an API key)."""

    __slots__ = ("_headers",)

    def __init__(self, headers: Mapping[str, str]) -> None:
        self._headers = dict(headers)

    def before_request(self, op: CompiledOp, request: httpx2.Request) -> Mapping[str, str]:
        return self._headers


class AsyncStaticHeaderAuth(StaticHeaderAuth):
    async def before_request(self, op: CompiledOp, request: httpx2.Request) -> Mapping[str, str]:  # type: ignore[override]
        return self._headers


__all__ = [
    "AsyncAuthHook",
    "AsyncNoAuth",
    "AsyncStaticHeaderAuth",
    "AuthHook",
    "NoAuth",
    "StaticHeaderAuth",
]
