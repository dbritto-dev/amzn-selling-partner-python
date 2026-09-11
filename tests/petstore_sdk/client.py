"""Generated clients for petstore_sdk (codegen/, oagen). Do not edit by hand."""

from __future__ import annotations

from typing import Any

from petstore_sdk.apis import APIs, AsyncAPIs

from amzn_selling_partner.runtime._base_client import AsyncAPIClient, SyncAPIClient


class Client(SyncAPIClient, APIs):
    _package = "petstore_sdk"

    def __init__(self, *, base_url: str, **kwargs: Any) -> None:
        super().__init__(base_url=base_url, **kwargs)


class AsyncClient(AsyncAPIClient, AsyncAPIs):
    _package = "petstore_sdk"

    def __init__(self, *, base_url: str, **kwargs: Any) -> None:
        super().__init__(base_url=base_url, **kwargs)


__all__ = ["AsyncClient", "Client"]
