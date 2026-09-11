"""Generic ``Client`` / ``AsyncClient``: the runtime plus the generated APIs.

``client.<api>`` is a typed container (``.v0``, ``.v2026_01_01``, ``.latest``,
``.versions``) whose resource modules are imported on first access;
``preload()`` imports and warms everything. The Amazon-preconfigured clients
(``SellingPartner`` / ``AsyncSellingPartner``) live in ``plugins.amazon_spapi``.
"""

from __future__ import annotations

from typing import Any

from .apis import APIs, AsyncAPIs
from .runtime._base_client import AsyncAPIClient, SyncAPIClient
from .runtime._resources import AsyncResource, SyncResource


class Client(SyncAPIClient, APIs):
    """Synchronous client over the generated APIs.

    Parameters
    ----------
    base_url:
        Server URL (e.g. ``Region.NA.base_url()``).
    Remaining keyword arguments are ``SyncAPIClient`` options (timeouts,
    retries, ``http_client=``, ``transport=``, ``auth=``, ``throttle=``, ...).
    """

    _package = __package__ or "amzn_selling_partner"

    def __init__(self, *, base_url: str, **kwargs: Any) -> None:
        super().__init__(base_url=base_url, **kwargs)


class AsyncClient(AsyncAPIClient, AsyncAPIs):
    """Asynchronous client over the generated APIs; see ``Client``."""

    _package = __package__ or "amzn_selling_partner"

    def __init__(self, *, base_url: str, **kwargs: Any) -> None:
        super().__init__(base_url=base_url, **kwargs)


def __getattr__(name: str) -> Any:
    if name in ("SellingPartner", "AsyncSellingPartner"):
        from .plugins.amazon_spapi import AsyncSellingPartner, SellingPartner

        return {"SellingPartner": SellingPartner, "AsyncSellingPartner": AsyncSellingPartner}[name]
    raise AttributeError(name)


__all__ = ["AsyncClient", "AsyncResource", "Client", "SyncResource"]
