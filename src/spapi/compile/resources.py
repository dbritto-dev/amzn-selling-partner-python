"""Group ``CompiledOp``s into Resource classes with real methods.

One factory produces both variants; the async method differs only by ``await``.
Method objects get ``__name__``, ``__qualname__``, ``__doc__`` and
``__signature__`` so that ``help()``, IDEs and ``inspect`` see the operation's
keyword-only parameters.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from .models import ModelNamespace
from .naming import identifier, snake_case
from .operations import CompiledOp

if TYPE_CHECKING:
    from ..runtime._base_client import AsyncAPIClient, SyncAPIClient

GroupBy = Literal["file", "tag", "path_prefix"]


class _ResourceBase:
    """Base for generated resource classes."""

    _ops: dict[str, CompiledOp] = {}
    _resource_name: str = ""
    models: ModelNamespace

    def __init__(self, client: Any, models: ModelNamespace) -> None:
        self._client = client
        self.models = models

    @property
    def operations(self) -> dict[str, CompiledOp]:
        return dict(self._ops)

    def operation(self, name: str) -> CompiledOp:
        """Look up a compiled operation by method name or operationId."""
        op = self._ops.get(name)
        if op is None:
            for candidate in self._ops.values():
                if candidate.operation_id == name:
                    return candidate
            raise KeyError(name)
        return op

    def __dir__(self) -> list[str]:
        return sorted(set(self._ops) | {"models", "operations", "operation"} | set(super().__dir__()))

    def __iter__(self) -> Iterator[str]:
        return iter(self._ops)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self._resource_name}: {len(self._ops)} operations>"


class SyncResource(_ResourceBase):
    _client: SyncAPIClient


class AsyncResource(_ResourceBase):
    _client: AsyncAPIClient


def _sync_method(op: CompiledOp) -> Callable[..., Any]:
    def method(self: SyncResource, **kwargs: Any) -> Any:
        return self._client._call(op, kwargs)  # pyright: ignore[reportPrivateUsage]

    _decorate(method, op)
    return method


def _async_method(op: CompiledOp) -> Callable[..., Any]:
    async def method(self: AsyncResource, **kwargs: Any) -> Any:
        return await self._client._call(op, kwargs)  # pyright: ignore[reportPrivateUsage]

    _decorate(method, op)
    return method


_SELF = inspect.Parameter("self", inspect.Parameter.POSITIONAL_ONLY)


def _decorate(fn: Any, op: CompiledOp) -> None:
    fn.__name__ = op.name
    fn.__qualname__ = op.name
    fn.__doc__ = op.doc
    # the stored signature has no ``self``; bound methods drop the first parameter
    fn.__signature__ = op.signature.replace(parameters=[_SELF, *op.signature.parameters.values()])
    fn.__spapi_op__ = op


@dataclass(slots=True, frozen=True)
class ResourcePair:
    name: str
    sync_cls: type[SyncResource]
    async_cls: type[AsyncResource]
    ops: tuple[CompiledOp, ...]


def build_resource(name: str, ops: Iterable[CompiledOp]) -> ResourcePair:
    ops_t = tuple(ops)
    by_name = {op.name: op for op in ops_t}
    cls_name = "".join(p.capitalize() for p in snake_case(name).split("_")) or "Resource"
    sync_ns: dict[str, Any] = {"_ops": by_name, "_resource_name": name, "__slots__": ("_client", "models")}
    async_ns: dict[str, Any] = {"_ops": by_name, "_resource_name": name, "__slots__": ("_client", "models")}
    for op in ops_t:
        sync_ns[op.name] = _sync_method(op)
        async_ns[op.name] = _async_method(op)
    sync_cls = type(cls_name, (SyncResource,), sync_ns)
    async_cls = type("Async" + cls_name, (AsyncResource,), async_ns)
    return ResourcePair(name=name, sync_cls=sync_cls, async_cls=async_cls, ops=ops_t)


def build_resources(ops: Iterable[CompiledOp], *, name: str, group_by: GroupBy = "file") -> dict[str, ResourcePair]:
    """Group operations and build one resource pair per group.

    ``file`` -> one resource named ``name``; ``tag`` -> first tag (snake_case,
    untagged ops go to ``name``); ``path_prefix`` -> first path segment after
    the common prefix.
    """
    ops_t = tuple(ops)
    if group_by == "file":
        return {name: build_resource(name, ops_t)}
    groups: dict[str, list[CompiledOp]] = {}
    if group_by == "tag":
        for op in ops_t:
            key = identifier(snake_case(op.tags[0])) if op.tags else name
            groups.setdefault(key, []).append(op)
    else:
        common = _common_prefix([op.path for op in ops_t])
        for op in ops_t:
            rest = op.path[len(common) :].strip("/")
            seg = rest.split("/", 1)[0] if rest else ""
            key = identifier(snake_case(seg)) if seg and not seg.startswith("{") else name
            groups.setdefault(key, []).append(op)
    return {k: build_resource(k, v) for k, v in groups.items()}


def _common_prefix(paths: list[str]) -> str:
    if not paths:
        return ""
    split = [p.strip("/").split("/") for p in paths]
    prefix: list[str] = []
    for parts in zip(*split, strict=False):
        if len(set(parts)) == 1 and not parts[0].startswith("{"):
            prefix.append(parts[0])
        else:
            break
    return "/" + "/".join(prefix)


__all__ = ["AsyncResource", "GroupBy", "ResourcePair", "SyncResource", "build_resource", "build_resources"]
