import asyncio
import datetime
import email.utils
import random
import time
import typing
from dataclasses import dataclass

import httpx2

from . import _exceptions, _transports

__all__ = [
    "NOT_GIVEN",
    "DEFAULT_TIMEOUT",
    "DEFAULT_MAX_RETRIES",
    "RequestOptions",
    "BaseClient",
    "SyncAPIClient",
    "AsyncAPIClient",
]


class _NotGiven:
    """Sentinel distinguishing "the caller didn't specify an auth override" (use this
    client's own SPAPIAuth) from `auth=None` (explicitly send unauthenticated, used for
    S3 pre-signed document downloads)."""

    def __repr__(self) -> str:
        return "NOT_GIVEN"


NOT_GIVEN: typing.Any = _NotGiven()

DEFAULT_TIMEOUT = _transports.DEFAULT_TIMEOUT
DEFAULT_MAX_RETRIES = 2
_INITIAL_RETRY_DELAY = 0.5
_MAX_RETRY_DELAY = 8.0
_RETRYABLE_STATUS_CODES = frozenset({408, 409, 429, 500, 502, 503, 504})
_RETRYABLE_TRANSPORT_EXCEPTIONS: typing.Tuple[typing.Type[Exception], ...] = (
    httpx2.TimeoutException,
    httpx2.ConnectError,
)


@dataclass(frozen=True, slots=True)
class RequestOptions:
    method: str
    url: str
    params: typing.Optional[typing.Mapping[str, typing.Any]] = None
    content: typing.Optional[bytes] = None
    headers: typing.Optional[typing.Mapping[str, str]] = None
    auth: typing.Any = NOT_GIVEN
    # Reports' `x-amzn-RateLimit-Limit`-driven proactive throttle sleep, preserved from the
    # pre-httpx2 implementation. The only call site that needs this is `get_reports`.
    rate_limit_sleep: bool = False


def _parse_retry_after(value: str) -> typing.Optional[float]:
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed is None:
        return None
    now = datetime.datetime.now(parsed.tzinfo or datetime.timezone.utc)
    return max(0.0, (parsed - now).total_seconds())


class BaseClient:
    """Non-I/O logic shared by `SyncAPIClient` and `AsyncAPIClient`: request building,
    retry decisions, backoff timing, and response/error parsing. No `await`, no I/O."""

    def __init__(
        self,
        *,
        base_url: str,
        auth: httpx2.Auth,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._auth = auth

    def _resolve_auth(self, options: RequestOptions) -> typing.Optional[httpx2.Auth]:
        # Resolved here (not left to the underlying httpx2 client's own `auth=` default)
        # so this SDK's auth is applied correctly even when the caller injected their own
        # `http_client=` (e.g. `DefaultAioHttpClient()`) that never configured one.
        return self._auth if options.auth is NOT_GIVEN else options.auth

    def _full_url(self, url: str) -> str:
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"{self.base_url.rstrip('/')}/{url.lstrip('/')}"

    def _should_retry_response(self, response: httpx2.Response) -> bool:
        return response.status_code in _RETRYABLE_STATUS_CODES

    def _should_retry_exception(self, exc: Exception) -> bool:
        return isinstance(exc, _RETRYABLE_TRANSPORT_EXCEPTIONS)

    def _retry_delay(
        self, remaining_retries: int, response: typing.Optional[httpx2.Response]
    ) -> float:
        if response is not None:
            retry_after_header = response.headers.get("retry-after")
            if retry_after_header is not None:
                parsed = _parse_retry_after(retry_after_header)
                if parsed is not None:
                    return parsed
        attempt = self.max_retries - remaining_retries
        backoff = min(_MAX_RETRY_DELAY, _INITIAL_RETRY_DELAY * (2**attempt))
        return backoff * random.random()  # noqa # nosec B311

    def _build_request(
        self,
        httpx_client: typing.Union[httpx2.Client, httpx2.AsyncClient],
        options: RequestOptions,
    ) -> httpx2.Request:
        return httpx_client.build_request(
            options.method,
            self._full_url(options.url),
            params=options.params,
            content=options.content,
            headers=options.headers,
        )

    def _make_status_error(self, response: httpx2.Response) -> _exceptions.APIStatusError:
        try:
            body: object = response.json()
        except ValueError:
            body = response.text
        exc_type = _exceptions.status_to_exception(response.status_code)
        return exc_type(
            f"Request failed with status {response.status_code}", response=response, body=body
        )

    def _map_transport_exception(
        self, exc: Exception, request: httpx2.Request
    ) -> _exceptions.SPAPIError:
        if isinstance(exc, httpx2.TimeoutException):
            return _exceptions.APITimeoutError(request=request)
        return _exceptions.APIConnectionError(request=request)

    def _rate_limit_sleep_seconds(self, response: httpx2.Response) -> float:
        return float(response.headers.get("x-amzn-RateLimit-Limit", 0.03)) * 100


class SyncAPIClient(BaseClient):
    def __init__(
        self,
        *,
        base_url: str,
        auth: httpx2.Auth,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: typing.Optional[httpx2.Client] = None,
        transport: typing.Optional[httpx2.BaseTransport] = None,
        limits: typing.Optional[httpx2.Limits] = None,
    ) -> None:
        super().__init__(base_url=base_url, auth=auth, timeout=timeout, max_retries=max_retries)
        self._provided_http_client = http_client
        self._transport = transport
        self._limits = limits or _transports.DEFAULT_LIMITS
        self.__httpx_client: typing.Optional[httpx2.Client] = None

    @property
    def _httpx_client(self) -> httpx2.Client:
        if self.__httpx_client is None:
            self.__httpx_client = self._provided_http_client or _transports.DefaultHttpxClient(
                timeout=httpx2.Timeout(self.timeout),
                transport=self._transport,
                limits=self._limits,
            )
        return self.__httpx_client

    def _request(self, options: RequestOptions) -> httpx2.Response:
        request = self._build_request(self._httpx_client, options)
        auth = self._resolve_auth(options)
        remaining_retries = self.max_retries

        while True:
            try:
                response = self._httpx_client.send(request, auth=auth)
            except httpx2.HTTPError as exc:
                if remaining_retries > 0 and self._should_retry_exception(exc):
                    time.sleep(self._retry_delay(remaining_retries, None))
                    remaining_retries -= 1
                    continue
                raise self._map_transport_exception(exc, request) from exc

            if options.rate_limit_sleep:
                time.sleep(self._rate_limit_sleep_seconds(response))

            if (
                response.is_error
                and remaining_retries > 0
                and self._should_retry_response(response)
            ):
                time.sleep(self._retry_delay(remaining_retries, response))
                remaining_retries -= 1
                continue

            if response.is_error:
                raise self._make_status_error(response)

            return response

    def close(self) -> None:
        if self.__httpx_client is not None:
            self.__httpx_client.close()

    def __enter__(self) -> "SyncAPIClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


class AsyncAPIClient(BaseClient):
    def __init__(
        self,
        *,
        base_url: str,
        auth: httpx2.Auth,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: typing.Optional[httpx2.AsyncClient] = None,
        transport: typing.Optional[httpx2.AsyncBaseTransport] = None,
        limits: typing.Optional[httpx2.Limits] = None,
    ) -> None:
        super().__init__(base_url=base_url, auth=auth, timeout=timeout, max_retries=max_retries)
        self._provided_http_client = http_client
        self._transport = transport
        self._limits = limits or _transports.DEFAULT_LIMITS
        self.__httpx_client: typing.Optional[httpx2.AsyncClient] = None
        self.__client_lock = asyncio.Lock()

    async def _get_httpx_client(self) -> httpx2.AsyncClient:
        if self.__httpx_client is None:
            async with self.__client_lock:
                if self.__httpx_client is None:
                    self.__httpx_client = (
                        self._provided_http_client
                        or _transports.DefaultAsyncHttpxClient(
                            timeout=httpx2.Timeout(self.timeout),
                            transport=self._transport,
                            limits=self._limits,
                        )
                    )
        return self.__httpx_client

    async def _request(self, options: RequestOptions) -> httpx2.Response:
        httpx_client = await self._get_httpx_client()
        request = self._build_request(httpx_client, options)
        auth = self._resolve_auth(options)
        remaining_retries = self.max_retries

        while True:
            try:
                response = await httpx_client.send(request, auth=auth)
            except httpx2.HTTPError as exc:
                if remaining_retries > 0 and self._should_retry_exception(exc):
                    await asyncio.sleep(self._retry_delay(remaining_retries, None))
                    remaining_retries -= 1
                    continue
                raise self._map_transport_exception(exc, request) from exc

            if options.rate_limit_sleep:
                await asyncio.sleep(self._rate_limit_sleep_seconds(response))

            if (
                response.is_error
                and remaining_retries > 0
                and self._should_retry_response(response)
            ):
                await asyncio.sleep(self._retry_delay(remaining_retries, response))
                remaining_retries -= 1
                continue

            if response.is_error:
                raise self._make_status_error(response)

            return response

    async def aclose(self) -> None:
        if self.__httpx_client is not None:
            await self.__httpx_client.aclose()

    async def __aenter__(self) -> "AsyncAPIClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
