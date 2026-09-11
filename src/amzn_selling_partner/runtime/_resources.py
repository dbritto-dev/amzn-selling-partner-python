"""Base classes for the generated resource classes (``resources/<api>/<version>.py``)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, ClassVar

from ._op import Op

if TYPE_CHECKING:
    from ._base_client import AsyncAPIClient, SyncAPIClient


class _ResourceBase:
    __slots__ = ("_client",)

    _ops: ClassVar[dict[str, Op]] = {}
    _resource_name: ClassVar[str] = ""
    #: the models module of this API version (``client.orders.v0.models.Order``)
    models: ClassVar[Any] = None

    def __init__(self, client: Any) -> None:
        self._client = client

    @property
    def operations(self) -> dict[str, Op]:
        return dict(self._ops)

    def operation(self, name: str) -> Op:
        """Look up an operation by method name or operationId."""
        op = self._ops.get(name)
        if op is None:
            for candidate in self._ops.values():
                if candidate.operation_id == name:
                    return candidate
            raise KeyError(name)
        return op

    def warm(self) -> None:
        """Build every response/error adapter of this resource (preload)."""
        for op in self._ops.values():
            op.warm()

    def __iter__(self) -> Iterator[str]:
        return iter(self._ops)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self._resource_name}: {len(self._ops)} operations>"


class SyncResource(_ResourceBase):
    __slots__ = ()
    _client: SyncAPIClient


class AsyncResource(_ResourceBase):
    __slots__ = ()
    _client: AsyncAPIClient


__all__ = ["AsyncResource", "SyncResource"]
