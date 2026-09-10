"""Pagination descriptor and page objects.

``Pagination`` describes *where* the token and the items live using the wire
(spec) field names; the compiler turns it into getters for both model and raw
mode. ``SyncPage`` / ``AsyncPage`` fetch the next page through the same client
path as the first call (retries, throttling, auth), only swapping the token
parameter and, when ``drop_params_on_next`` is set, dropping every other
non-path argument.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from ._types import NOT_GIVEN, NotGiven

if TYPE_CHECKING:
    from ..compile.operations import CompiledOp
    from ._base_client import AsyncAPIClient, SyncAPIClient
    from ._types import RequestOptions

T = TypeVar("T")


@dataclass(slots=True, frozen=True, kw_only=True)
class Pagination:
    items_path: str
    next_token_path: str
    next_token_param: str
    prev_token_path: str | None = None
    drop_params_on_next: bool = False
    keep_params: tuple[str, ...] = ()
    items_is_object: bool = False
    #: how the descriptor was produced ("heuristic", "plugin", "call")
    source: str = "plugin"


Getter = Callable[[Any], Any]


@dataclass(slots=True, frozen=True, kw_only=True)
class CompiledPagination:
    """Per-operation, precomputed accessors. Built once by the compiler."""

    descriptor: Pagination
    token_kw: str  # python keyword of the next-token parameter
    keep_kws: frozenset[str] = frozenset()  # python kwargs that survive a drop
    items_model: Getter = field(repr=False)
    token_model: Getter = field(repr=False)
    prev_model: Getter | None = field(default=None, repr=False)
    items_raw: Getter = field(repr=False)
    token_raw: Getter = field(repr=False)
    prev_raw: Getter | None = field(default=None, repr=False)

    def next_kwargs(self, kwargs: dict[str, Any], token: str) -> dict[str, Any]:
        if self.descriptor.drop_params_on_next:
            new = {k: v for k, v in kwargs.items() if k in self.keep_kws}
        else:
            new = dict(kwargs)
        new[self.token_kw] = token
        return new


def make_getter(path: str, *, python_names: Callable[[str], str] | None = None) -> Getter:
    """Compile a dotted path into a function; missing segments yield ``None``.

    Works on both models (attribute access) and dicts (item access); the
    model getter receives already snake-cased names via ``python_names``.
    """
    parts = tuple(path.split(".")) if path else ()
    if python_names is not None:
        parts = tuple(python_names(p) for p in parts)
    if not parts:
        return lambda obj: obj
    if len(parts) == 1:
        (a,) = parts

        def get1(obj: Any) -> Any:
            if obj is None:
                return None
            if isinstance(obj, dict):
                return obj.get(a)
            return getattr(obj, a, None)

        return get1

    def getn(obj: Any) -> Any:
        for p in parts:
            if obj is None:
                return None
            obj = obj.get(p) if isinstance(obj, dict) else getattr(obj, p, None)
        return obj

    return getn


class _PageBase(Generic[T]):
    __slots__ = ("_client", "_kwargs", "_options", "_op", "_raw_mode", "_spec", "raw")

    raw: Any

    def __init__(
        self,
        client: Any,
        op: CompiledOp,
        kwargs: dict[str, Any],
        options: RequestOptions,
        spec: CompiledPagination,
        raw: Any,
        raw_mode: bool,
    ) -> None:
        self._client = client
        self._op = op
        self._kwargs = kwargs
        self._options = options
        self._spec = spec
        self._raw_mode = raw_mode
        self.raw = raw

    @property
    def items(self) -> list[T]:
        items = (self._spec.items_raw if self._raw_mode else self._spec.items_model)(self.raw)
        if items is None:
            return []
        if self._spec.descriptor.items_is_object:
            return [items]
        return items  # type: ignore[no-any-return]

    @property
    def next_token(self) -> str | None:
        tok = (self._spec.token_raw if self._raw_mode else self._spec.token_model)(self.raw)
        return tok if isinstance(tok, str) and tok else None

    @property
    def prev_token(self) -> str | None:
        g = self._spec.prev_raw if self._raw_mode else self._spec.prev_model
        if g is None:
            return None
        tok = g(self.raw)
        return tok if isinstance(tok, str) and tok else None

    @property
    def has_next(self) -> bool:
        return self.next_token is not None

    def _next_kwargs(self) -> dict[str, Any] | None:
        token = self.next_token
        if token is None:
            return None
        return self._spec.next_kwargs(self._kwargs, token)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} items={len(self.items)} has_next={self.has_next}>"


class SyncPage(_PageBase[T]):
    __slots__ = ()

    _client: SyncAPIClient

    def next_page(self) -> SyncPage[T] | None:
        kwargs = self._next_kwargs()
        if kwargs is None:
            return None
        return self._client._call(self._op, kwargs, self._options)  # type: ignore[return-value]

    def pages(self) -> Iterator[SyncPage[T]]:
        page: SyncPage[T] | None = self
        while page is not None:
            yield page
            page = page.next_page()

    def __iter__(self) -> Iterator[T]:
        for page in self.pages():
            yield from page.items

    def all(self) -> list[T]:
        return list(self)


class AsyncPage(_PageBase[T]):
    __slots__ = ()

    _client: AsyncAPIClient

    async def next_page(self) -> AsyncPage[T] | None:
        kwargs = self._next_kwargs()
        if kwargs is None:
            return None
        return await self._client._call(self._op, kwargs, self._options)  # type: ignore[return-value]

    async def pages(self) -> AsyncIterator[AsyncPage[T]]:
        page: AsyncPage[T] | None = self
        while page is not None:
            yield page
            page = await page.next_page()

    async def __aiter__(self) -> AsyncIterator[T]:
        async for page in self.pages():
            for item in page.items:
                yield item

    async def all(self) -> list[T]:
        return [item async for item in self]


def paginate_option(value: Pagination | None | NotGiven) -> Pagination | None | NotGiven:
    return NOT_GIVEN if value is NOT_GIVEN else value


__all__ = ["AsyncPage", "CompiledPagination", "Pagination", "SyncPage", "make_getter"]
