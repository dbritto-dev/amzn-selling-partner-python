"""``BaseClient`` (all non-I/O logic) and the two thin I/O layers
``SyncAPIClient`` / ``AsyncAPIClient``.

Per-call path: ``method(**kwargs)`` -> ``_call`` -> ``_build_request`` (uses
the precomputed builders on ``CompiledOp``) -> send/retry loop -> ``_finish``
(prebuilt ``TypeAdapter.validate_json`` on the body bytes, page wrapping).
Nothing in this path touches the spec, merges header dicts or constructs
pydantic models for options.
"""

from __future__ import annotations

import asyncio
import email.utils
import logging
import random
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import quote

import httpx2
from pydantic import ValidationError
from pydantic_core import from_json

from ._errors import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    RateLimitError,
    status_error_class,
)
from ._pagination import AsyncPage, CompiledPagination, Pagination, SyncPage
from ._stream import AsyncStream, Stream
from ._throttle import AsyncThrottler, RateLimit, Throttler, TokenBucket
from ._transports import DEFAULT_LIMITS, DEFAULT_TIMEOUT, async_transport, sync_transport
from ._types import DEFAULT_OPTIONS, NOT_GIVEN, HeaderPairs, RequestOptions

if TYPE_CHECKING:
    from ..compile.operations import CompiledOp
    from ._auth import AsyncAuthHook, AuthHook

log = logging.getLogger("spapi.runtime.client")

DEFAULT_RETRY_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
_RESERVED_KWARGS = frozenset({"raw", "paginate", "request_options"})


def _user_agent() -> str:
    from .. import __version__

    return f"spapi/{__version__} httpx2/{httpx2.__version__}"


@dataclass(slots=True, frozen=True, kw_only=True)
class ClientOptions:
    """Immutable snapshot of the client's configuration (for introspection)."""

    base_url: str
    timeout: httpx2.Timeout
    total_timeout: float | None
    max_retries: int
    retry_statuses: frozenset[int]
    backoff_initial: float
    backoff_max: float
    limits: httpx2.Limits
    request_id_header: str
    rate_hint_header: str | None
    throttle: bool


class BaseClient:
    """Everything that does not perform I/O."""

    _client: Any
    _auth: Any

    def __init__(
        self,
        *,
        base_url: str,
        headers: Mapping[str, str] | None = None,
        timeout: httpx2.Timeout | float | None = DEFAULT_TIMEOUT,
        total_timeout: float | None = None,
        max_retries: int = 2,
        retry_statuses: frozenset[int] | set[int] = DEFAULT_RETRY_STATUSES,
        backoff_initial: float = 0.5,
        backoff_max: float = 8.0,
        auth: Any = None,
        throttle: bool = True,
        default_rate_limit: RateLimit | None = None,
        limits: httpx2.Limits = DEFAULT_LIMITS,
        transport: Any = None,
        http_client: Any = None,
        request_id_header: str = "x-request-id",
        rate_hint_header: str | None = None,
        user_agent: str | None = None,
        verify: Any = True,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout if isinstance(timeout, httpx2.Timeout) else httpx2.Timeout(timeout)
        self._timeout_ext: dict[str, Any] = {"timeout": self._timeout.as_dict()}
        self._total_timeout = total_timeout
        self._max_retries = max_retries
        self._retry_statuses = frozenset(retry_statuses)
        self._backoff_initial = backoff_initial
        self._backoff_max = backoff_max
        self._auth = auth
        self._limits = limits
        self._transport = transport
        self._client = http_client
        self._owns_client = http_client is None
        self._request_id_header = request_id_header
        self._rate_hint_header = rate_hint_header
        self._verify = verify
        self._throttle_enabled = throttle
        self._default_rate_limit = default_rate_limit
        self._throttler: Throttler | None = None
        pairs: list[tuple[str, str]] = [
            ("Accept", "application/json"),
            ("User-Agent", user_agent or _user_agent()),
        ]
        if headers:
            pairs.extend(headers.items())
        self._default_headers: HeaderPairs = tuple(pairs)

    # -- introspection -------------------------------------------------------------

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def options(self) -> ClientOptions:
        return ClientOptions(
            base_url=self._base_url,
            timeout=self._timeout,
            total_timeout=self._total_timeout,
            max_retries=self._max_retries,
            retry_statuses=self._retry_statuses,
            backoff_initial=self._backoff_initial,
            backoff_max=self._backoff_max,
            limits=self._limits,
            request_id_header=self._request_id_header,
            rate_hint_header=self._rate_hint_header,
            throttle=self._throttle_enabled,
        )

    @property
    def default_headers(self) -> HeaderPairs:
        return self._default_headers

    def set_base_url(self, url: str) -> None:
        self._base_url = url.rstrip("/")

    # -- request building ----------------------------------------------------------

    def _prepare(self, op: CompiledOp, kwargs: dict[str, Any]) -> RequestOptions:
        options = DEFAULT_OPTIONS
        if kwargs.keys() & _RESERVED_KWARGS:
            ro = kwargs.pop("request_options", None)
            raw = kwargs.pop("raw", False)
            paginate = kwargs.pop("paginate", NOT_GIVEN)
            options = ro if ro is not None else DEFAULT_OPTIONS
            if raw or paginate is not NOT_GIVEN:
                options = replace(
                    options,
                    raw=bool(raw) or options.raw,
                    paginate=paginate if paginate is not NOT_GIVEN else options.paginate,
                )
        op.check_kwargs(kwargs)
        return options

    def _build_request(self, op: CompiledOp, kwargs: dict[str, Any], options: RequestOptions) -> httpx2.Request:
        url = op.build_url(self._base_url, kwargs)
        if options.extra_query:
            extra = "&".join(f"{quote(str(k), safe='')}={quote(str(v), safe='')}" for k, v in options.extra_query.items())
            url = f"{url}{'&' if '?' in url else '?'}{extra}"
        headers = self._default_headers
        if op.header_params:
            headers = headers + op.build_headers(kwargs)
        if options.extra_headers:
            headers = headers + tuple(options.extra_headers.items())
        content: bytes | None = None
        if op.body is not None:
            encoded = op.encode_body(kwargs.get("body", NOT_GIVEN))
            if encoded is not None:
                content, content_type = encoded
                headers = headers + (("Content-Type", content_type),)
        if options.timeout is None:
            extensions = self._timeout_ext
        else:
            t = options.timeout if isinstance(options.timeout, httpx2.Timeout) else httpx2.Timeout(options.timeout)
            extensions = {"timeout": t.as_dict()}
        if options.auth is not None:
            extensions = {**extensions, "spapi_auth": options.auth}
        return httpx2.Request(op.method, url, headers=headers, content=content, extensions=extensions)

    # -- retry policy ----------------------------------------------------------------

    def _backoff(self, attempt: int) -> float:
        delay = min(self._backoff_max, self._backoff_initial * (2.0**attempt))
        return delay * (0.5 + random.random() / 2.0)  # noqa: S311 - jitter, not security

    def _retry_delay(self, attempt: int, response: httpx2.Response, bucket: TokenBucket | None) -> float:
        retry_after = _parse_retry_after(response.headers.get("retry-after"))
        if retry_after is None and self._rate_hint_header:
            hint = response.headers.get(self._rate_hint_header)
            if hint:
                try:
                    rate = float(hint)
                except ValueError:
                    rate = 0.0
                if rate > 0:
                    retry_after = 1.0 / rate
                    if bucket is not None:
                        bucket.update_rate(rate)
        if retry_after is not None:
            delay = min(max(retry_after, 0.0), self._backoff_max * 8) * (1.0 + random.random() * 0.25)  # noqa: S311
        else:
            delay = self._backoff(attempt)
        if response.status_code == 429 and bucket is not None:
            bucket.penalize(delay)
        return delay

    def _bucket(self, op: CompiledOp) -> TokenBucket | None:
        throttler = self._throttler
        if throttler is None:
            return None
        return throttler.bucket(op.key, op.rate_limit)

    # -- response handling -----------------------------------------------------------

    def _finish(self, op: CompiledOp, kwargs: dict[str, Any], options: RequestOptions, response: httpx2.Response) -> Any:
        body = response.content
        if options.raw:
            if not body:
                result = None
            elif op.decoder_for(response.status_code).kind == "json" or "json" in response.headers.get("content-type", ""):
                result = from_json(body)
            else:
                result = body
        else:
            try:
                result = op.decoder_for(response.status_code).decode(body, lambda: response.text)
            except ValidationError as exc:
                raise APIResponseValidationError(f"{op.operation_id}: response body does not match the spec: {exc}", response=response, cause=exc) from exc
        pagination = self._pagination_for(op, options)
        if pagination is None:
            return result
        return self._page_class(self, op, kwargs, options, pagination, result, options.raw)

    _page_class: Any = SyncPage

    @staticmethod
    def _pagination_for(op: CompiledOp, options: RequestOptions) -> CompiledPagination | None:
        override = options.paginate
        if override is NOT_GIVEN:
            return op.pagination
        if override is None:
            return None
        from ..compile.operations import compile_pagination

        assert isinstance(override, Pagination)
        return compile_pagination(override, op.query_params, op.path_params, op.header_params)

    def _make_error(self, op: CompiledOp, response: httpx2.Response) -> APIStatusError:
        status = response.status_code
        body = response.content
        parsed: Any = None
        if body:
            decoder = op.error_decoders.get(status) or op.default_error
            if decoder is not None:
                try:
                    parsed = decoder.adapter.validate_json(body)
                except ValidationError:
                    parsed = None
            if parsed is None:
                try:
                    parsed = from_json(body)
                except ValueError:
                    parsed = body
        request_id = response.headers.get(self._request_id_header)
        message = f"{op.operation_id}: HTTP {status} {response.reason_phrase}".rstrip()
        cls = status_error_class(status)
        if cls is RateLimitError:
            return RateLimitError(
                message,
                response=response,
                body=parsed,
                request_id=request_id,
                retry_after=_parse_retry_after(response.headers.get("retry-after")),
            )
        return cls(message, response=response, body=parsed, request_id=request_id)


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, dt.timestamp() - time.time())


# ------------------------------------------------------------------------------------


class SyncAPIClient(BaseClient):
    _client: httpx2.Client | None
    _auth: AuthHook | None
    _page_class = SyncPage

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self._throttle_enabled:
            self._throttler = Throttler(default=self._default_rate_limit)

    # -- lifecycle -------------------------------------------------------------------

    def _http(self) -> httpx2.Client:
        client = self._client
        if client is None:
            transport = self._transport or sync_transport(limits=self._limits, verify=self._verify)
            client = httpx2.Client(transport=transport, timeout=self._timeout, limits=self._limits)
            self._client = client
        return client

    @property
    def http_client(self) -> httpx2.Client:
        return self._http()

    @property
    def is_closed(self) -> bool:
        return self._client is not None and self._client.is_closed

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    # -- hot path --------------------------------------------------------------------

    def _call(self, op: CompiledOp, kwargs: dict[str, Any], options: RequestOptions | None = None) -> Any:
        if options is None:
            options = self._prepare(op, kwargs)
        request = self._build_request(op, kwargs, options)
        if op.stream_default:
            return Stream(self._send(op, request, options, stream=True))
        response = self._send(op, request, options)
        return self._finish(op, kwargs, options, response)

    def stream(self, op: CompiledOp, **kwargs: Any) -> Stream:
        options = self._prepare(op, kwargs)
        request = self._build_request(op, kwargs, options)
        return Stream(self._send(op, request, options, stream=True))

    def _send(self, op: CompiledOp, request: httpx2.Request, options: RequestOptions, *, stream: bool = False) -> httpx2.Response:
        client = self._http()
        retries = self._max_retries if options.max_retries is None else options.max_retries
        bucket = self._bucket(op)
        auth = self._auth
        attempt = 0
        while True:
            if bucket is not None:
                bucket.acquire()
            if auth is not None:
                extra = auth.before_request(op, request)
                if extra:
                    request.headers.update(extra)
            try:
                response = client.send(request, stream=stream)
            except httpx2.TimeoutException as exc:
                if attempt >= retries:
                    raise APITimeoutError(request=request, cause=exc) from exc
                delay = self._backoff(attempt)
                log.debug("%s: timeout (%s); retry %d/%d in %.2fs", op.key, exc, attempt + 1, retries, delay)
                time.sleep(delay)
                attempt += 1
                continue
            except httpx2.TransportError as exc:
                if attempt >= retries:
                    raise APIConnectionError(str(exc) or "Connection error.", request=request, cause=exc) from exc
                delay = self._backoff(attempt)
                log.debug("%s: connection error (%s); retry %d/%d in %.2fs", op.key, exc, attempt + 1, retries, delay)
                time.sleep(delay)
                attempt += 1
                continue
            status = response.status_code
            if status < 400:
                return response
            if status in self._retry_statuses and attempt < retries:
                delay = self._retry_delay(attempt, response, bucket)
                response.close()
                log.debug("%s: HTTP %d; retry %d/%d in %.2fs", op.key, status, attempt + 1, retries, delay)
                time.sleep(delay)
                attempt += 1
                continue
            if stream:
                response.read()
            raise self._make_error(op, response)


class AsyncAPIClient(BaseClient):
    _client: httpx2.AsyncClient | None
    _auth: AsyncAuthHook | None
    _page_class = AsyncPage

    def __init__(self, *, prefer_aiohttp: bool = True, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._prefer_aiohttp = prefer_aiohttp
        if self._throttle_enabled:
            self._throttler = AsyncThrottler(default=self._default_rate_limit)

    def _http(self) -> httpx2.AsyncClient:
        client = self._client
        if client is None:
            transport = self._transport or async_transport(limits=self._limits, verify=self._verify, prefer_aiohttp=self._prefer_aiohttp)
            client = httpx2.AsyncClient(transport=transport, timeout=self._timeout, limits=self._limits)
            self._client = client
        return client

    @property
    def http_client(self) -> httpx2.AsyncClient:
        return self._http()

    @property
    def is_closed(self) -> bool:
        return self._client is not None and self._client.is_closed

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        await self.aclose()

    async def _call(self, op: CompiledOp, kwargs: dict[str, Any], options: RequestOptions | None = None) -> Any:
        if options is None:
            options = self._prepare(op, kwargs)
        request = self._build_request(op, kwargs, options)
        if op.stream_default:
            return AsyncStream(await self._send(op, request, options, stream=True))
        response = await self._send(op, request, options)
        return self._finish(op, kwargs, options, response)

    async def stream(self, op: CompiledOp, **kwargs: Any) -> AsyncStream:
        options = self._prepare(op, kwargs)
        request = self._build_request(op, kwargs, options)
        return AsyncStream(await self._send(op, request, options, stream=True))

    async def _send(self, op: CompiledOp, request: httpx2.Request, options: RequestOptions, *, stream: bool = False) -> httpx2.Response:
        client = self._http()
        retries = self._max_retries if options.max_retries is None else options.max_retries
        bucket = self._bucket(op)
        auth = self._auth
        total = self._total_timeout
        attempt = 0
        while True:
            if bucket is not None:
                await bucket.acquire()  # type: ignore[misc]
            if auth is not None:
                extra = await auth.before_request(op, request)
                if extra:
                    request.headers.update(extra)
            try:
                async with asyncio.timeout(total):
                    response = await client.send(request, stream=stream)
            except (httpx2.TimeoutException, TimeoutError) as exc:
                if attempt >= retries:
                    raise APITimeoutError(request=request, cause=exc) from exc
                delay = self._backoff(attempt)
                log.debug("%s: timeout (%s); retry %d/%d in %.2fs", op.key, exc, attempt + 1, retries, delay)
                await asyncio.sleep(delay)
                attempt += 1
                continue
            except httpx2.TransportError as exc:
                if attempt >= retries:
                    raise APIConnectionError(str(exc) or "Connection error.", request=request, cause=exc) from exc
                delay = self._backoff(attempt)
                log.debug("%s: connection error (%s); retry %d/%d in %.2fs", op.key, exc, attempt + 1, retries, delay)
                await asyncio.sleep(delay)
                attempt += 1
                continue
            status = response.status_code
            if status < 400:
                return response
            if status in self._retry_statuses and attempt < retries:
                delay = self._retry_delay(attempt, response, bucket)
                await response.aclose()
                log.debug("%s: HTTP %d; retry %d/%d in %.2fs", op.key, status, attempt + 1, retries, delay)
                await asyncio.sleep(delay)
                attempt += 1
                continue
            if stream:
                await response.aread()
            raise self._make_error(op, response)


__all__ = ["DEFAULT_RETRY_STATUSES", "AsyncAPIClient", "BaseClient", "ClientOptions", "SyncAPIClient"]
