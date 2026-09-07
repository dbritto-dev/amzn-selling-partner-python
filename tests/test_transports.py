import importlib
import sys

import pytest

import amzn_selling_partner._transports as transports_module


def test_default_aiohttp_client_raises_clear_error_when_extra_missing() -> None:
    """Simulates `httpx_aiohttp` not being installed by hiding it from the import
    system and reloading `_transports`, then restores the real module afterward so
    other tests keep using the genuine aiohttp-backed `DefaultAioHttpClient`.
    """
    original_httpx_aiohttp = sys.modules.get("httpx_aiohttp")
    original_httpx_aiohttp_httpx2 = sys.modules.get("httpx_aiohttp.httpx2")
    sys.modules["httpx_aiohttp"] = None  # type: ignore[assignment]
    sys.modules["httpx_aiohttp.httpx2"] = None  # type: ignore[assignment]
    try:
        importlib.reload(transports_module)
        with pytest.raises(RuntimeError, match="aiohttp"):
            transports_module.DefaultAioHttpClient()
    finally:
        if original_httpx_aiohttp is not None:
            sys.modules["httpx_aiohttp"] = original_httpx_aiohttp
        else:
            sys.modules.pop("httpx_aiohttp", None)
        if original_httpx_aiohttp_httpx2 is not None:
            sys.modules["httpx_aiohttp.httpx2"] = original_httpx_aiohttp_httpx2
        else:
            sys.modules.pop("httpx_aiohttp.httpx2", None)
        importlib.reload(transports_module)
