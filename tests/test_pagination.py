"""Pagination: the generated ``iter_<method>`` helpers and ``paginate`` / ``apaginate``."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx2
import pytest
from petstore_sdk.client import AsyncClient, Client
from petstore_sdk.http_client import AsyncTokenBucket, RateLimit, RequestOptions, TokenBucket, apaginate, paginate
from petstore_sdk.resources import OPERATIONS

from .conftest import requires_amazon

BASE = "https://api.example.com"

EXPECTED_AMAZON = {
    "orders_v0.getOrders": True,
    "orders_v0.getOrderItems": True,
    "orders_v0.getOrderItemsBuyerInfo": True,
    "orders_v0.getOrder": False,
    "listings_items_v2021_08_01.searchListingsItems": True,
    "finances_v0.listFinancialEvents": True,
}


def test_detection_matches_expected_list() -> None:
    assert {k for k, v in OPERATIONS.items() if v[3]} == {"petstore_v3.listPets", "petstore_v2.listPets", "petstore_v2.getOrders"}


@requires_amazon
def test_detection_amazon() -> None:
    from amzn_selling_partner.sdk.resources import OPERATIONS as AMAZON
    from amzn_selling_partner.sdk.resources.orders_v0 import OrdersV0Client

    for key, expected in EXPECTED_AMAZON.items():
        assert AMAZON[key][3] is expected, key
    assert sum(1 for v in AMAZON.values() if v[3]) == 69
    assert hasattr(OrdersV0Client, "iter_list_orders") and not hasattr(OrdersV0Client, "iter_get_order")


def _handler(seen: list[httpx2.Request]) -> Any:
    def handler(r: httpx2.Request) -> httpx2.Response:
        seen.append(r)
        tok = r.url.params.get("nextToken")
        n = int(tok[1:]) if tok else 0
        body: dict[str, Any] = {"items": [{"id": n * 2 + 1, "name": "a"}, {"id": n * 2 + 2, "name": "b"}]}
        if n < 3:
            body["nextToken"] = f"t{n + 1}"
        return httpx2.Response(200, json=body)

    return handler


def test_multi_page_order_sync_and_async_with_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    acquires: list[float] = []
    orig = TokenBucket.acquire

    def counting(self: TokenBucket) -> float:
        acquires.append(time.monotonic())
        return orig(self)

    monkeypatch.setattr(TokenBucket, "acquire", counting)
    aorig = AsyncTokenBucket.acquire

    async def acounting(self: AsyncTokenBucket) -> float:
        acquires.append(time.monotonic())
        return await aorig(self)

    monkeypatch.setattr(AsyncTokenBucket, "acquire", acounting)
    seen: list[httpx2.Request] = []
    fast = RateLimit(rate=1000, burst=2)
    api = Client(base_url=BASE, transport=httpx2.MockTransport(_handler(seen)), default_rate_limit=fast).petstore_v3
    assert [p.id for p in api.iter_list_pets(limit=2, tags=["x"])] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert len(seen) == 4 and len(acquires) == 4
    assert all("tags=x" in str(r.url) for r in seen)  # params kept on every page (no drop)

    async def go() -> list[int]:
        aseen: list[httpx2.Request] = []
        aapi = AsyncClient(base_url=BASE, transport=httpx2.MockTransport(_handler(aseen)), default_rate_limit=fast).petstore_v3
        ids = [x.id async for x in aapi.iter_list_pets(limit=2)]
        assert len(aseen) == 4
        return ids

    assert asyncio.run(go()) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert len(acquires) == 8


def test_paginate_drop_params_and_keep_params() -> None:
    calls: list[dict[str, Any]] = []

    def fn(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        n = len(calls)
        return {"items": [n], "nextToken": f"t{n}" if n < 3 else None}

    items = list(
        paginate(
            fn,
            {"limit": 2, "tags": ["a"], "status": "sold", "request_options": None},
            items=("items",),
            token=("nextToken",),
            token_param="next_token",
            drop_params_on_next=True,
            keep_params=("limit",),
        )
    )
    assert items == [1, 2, 3]
    assert calls[0] == {"limit": 2, "tags": ["a"], "status": "sold", "request_options": None}
    assert calls[1] == {"limit": 2, "tags": None, "status": None, "request_options": None, "next_token": "t1"}
    assert calls[2] == {"limit": 2, "tags": None, "status": None, "request_options": None, "next_token": "t2"}


def test_paginate_single_container_and_raw_paths() -> None:
    class Page:
        def __init__(self, n: int) -> None:
            self.payload = {"events": {"n": n}, "nextToken": f"t{n}" if n < 2 else None}

    def fn(**kwargs: Any) -> Any:
        n = int(kwargs["next_token"][1:]) + 1 if "next_token" in kwargs else 1
        return Page(n)

    pages = list(paginate(fn, {}, items=("payload", "events"), token=("payload", "nextToken"), token_param="next_token", single=True))
    assert pages == [{"n": 1}, {"n": 2}]

    async def afn(**kwargs: Any) -> Any:
        return {"Payload": {"Items": [1, 2], "NextToken": None}}

    async def go() -> list[int]:
        raw = RequestOptions(raw=True)
        return [
            x
            async for x in apaginate(
                afn,
                {"request_options": raw},
                items=("payload", "items"),
                token=("payload", "next_token"),
                token_param="next_token",
                wire_items=("Payload", "Items"),
                wire_token=("Payload", "NextToken"),
            )
        ]

    assert asyncio.run(go()) == [1, 2]  # raw responses use the wire paths
