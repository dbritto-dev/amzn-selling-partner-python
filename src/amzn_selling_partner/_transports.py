import typing

import httpx2

__all__ = [
    "DEFAULT_TIMEOUT",
    "DEFAULT_LIMITS",
    "DefaultHttpxClient",
    "DefaultAsyncHttpxClient",
    "DefaultAioHttpClient",
]

DEFAULT_TIMEOUT = 60.0
DEFAULT_LIMITS = httpx2.Limits(max_connections=100, max_keepalive_connections=50)


class DefaultHttpxClient(httpx2.Client):
    """An `httpx2.Client` carrying this SDK's default timeout/connection-pool settings.

    Pass an instance as `http_client=` to `Client(...)` if you want to customize the
    underlying client (proxies, mounts, custom transport, ...) without losing these
    defaults — building a plain `httpx2.Client()` yourself would use httpx2's own
    defaults instead.
    """

    def __init__(self, **kwargs: typing.Any) -> None:
        kwargs.setdefault("timeout", httpx2.Timeout(DEFAULT_TIMEOUT))
        kwargs.setdefault("limits", DEFAULT_LIMITS)
        super().__init__(**kwargs)


class DefaultAsyncHttpxClient(httpx2.AsyncClient):
    """Async equivalent of `DefaultHttpxClient`, for `http_client=` on `AsyncClient(...)`."""

    def __init__(self, **kwargs: typing.Any) -> None:
        kwargs.setdefault("timeout", httpx2.Timeout(DEFAULT_TIMEOUT))
        kwargs.setdefault("limits", DEFAULT_LIMITS)
        super().__init__(**kwargs)


try:
    from httpx_aiohttp.httpx2 import Httpx2AiohttpClient
except ImportError:

    class DefaultAioHttpClient(httpx2.AsyncClient):  # type: ignore[no-redef]
        """Raises on construction — install the `aiohttp` extra to use this client."""

        def __init__(self, **_kwargs: typing.Any) -> None:
            raise RuntimeError(
                "To use DefaultAioHttpClient you must install this package with the "
                "`aiohttp` extra: `pip install amzn-selling-partner[aiohttp]` (or "
                "`uv sync --extra aiohttp`)."
            )

else:

    class DefaultAioHttpClient(Httpx2AiohttpClient):  # type: ignore[no-redef]
        """An `httpx2.AsyncClient` backed by an aiohttp transport, with this SDK's default
        timeout/connection-pool settings. Pass an instance as `http_client=` to
        `AsyncClient(...)` to opt into aiohttp — it is never selected automatically, even
        when the `aiohttp` extra happens to be installed.
        """

        def __init__(self, **kwargs: typing.Any) -> None:
            kwargs.setdefault("timeout", httpx2.Timeout(DEFAULT_TIMEOUT))
            kwargs.setdefault("limits", DEFAULT_LIMITS)
            super().__init__(**kwargs)
