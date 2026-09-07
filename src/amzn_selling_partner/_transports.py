import httpx2

__all__ = ["DEFAULT_LIMITS", "default_async_transport"]

DEFAULT_LIMITS = httpx2.Limits(max_connections=100, max_keepalive_connections=50)


def default_async_transport(*, limits: httpx2.Limits) -> httpx2.AsyncBaseTransport:
    """Aiohttp-backed transport when the `aiohttp` extra is installed, else httpx2's default."""
    try:
        from httpx_aiohttp.httpx2 import AiohttpTransport
    except ImportError:
        return httpx2.AsyncHTTPTransport(limits=limits)
    return AiohttpTransport(limits=limits)
