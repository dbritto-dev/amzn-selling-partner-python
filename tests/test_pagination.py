"""Pagination descriptors baked into the generated tables + the page objects."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx2
import pytest
from petstore_sdk.client import AsyncClient, Client
from petstore_sdk.resources.petstore.v2 import PetstoreV2
from petstore_sdk.resources.petstore.v3 import PetstoreV3

from amzn_selling_partner.runtime import Pagination, RateLimit
from amzn_selling_partner.runtime._pagination import compile_pagination
from amzn_selling_partner.runtime._throttle import AsyncTokenBucket, TokenBucket

from .conftest import requires_amazon

BASE = "https://api.example.com/v1"

EXPECTED = {
    PetstoreV3: {"listPets": ("items", "nextToken", "nextToken")},
    PetstoreV2: {
        "listPets": ("payload.Pets", "payload.NextToken", "NextToken"),
        "getOrders": ("payload.orders", "payload.pagination.nextToken", "NextToken"),
    },
}
EXPECTED_AMAZON = {
    ("orders", "v0"): {
        "getOrders": "payload.Orders",
        "getOrderItems": "payload.OrderItems",
        "getOrderItemsBuyerInfo": "payload.OrderItems",
    },
    ("listings_items", "v2021_08_01"): {"searchListingsItems": "items"},
}


@pytest.mark.parametrize("cls", [PetstoreV3, PetstoreV2])
def test_detection_matches_expected_list(cls: Any) -> None:
    found = {
        op.operation_id: (p.items_path, p.next_token_path, p.next_token_param)
        for op in cls._ops.values()
        if (p := op.pagination) is not None
    }
    assert found == EXPECTED[cls]
    assert all(op.pagination.source == "heuristic" for op in cls._ops.values() if op.pagination is not None)


@requires_amazon
@pytest.mark.parametrize("key", list(EXPECTED_AMAZON))
def test_detection_amazon(key: tuple[str, str]) -> None:
    import importlib

    module = importlib.import_module(f"amzn_selling_partner.resources.{key[0]}.{key[1]}")
    ops = getattr(module, module.__all__[1])._ops
    found = {op.operation_id: p.items_path for op in ops.values() if (p := op.pagination) is not None}
    assert found == EXPECTED_AMAZON[key]


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

    async def acounting(self: AsyncTokenBucket) -> float:
        acquires.append(time.monotonic())
        return await aorig(self)

    aorig = AsyncTokenBucket.acquire
    monkeypatch.setattr(AsyncTokenBucket, "acquire", acounting)
    seen: list[httpx2.Request] = []
    fast = RateLimit(rate=1000, burst=2)
    api = Client(base_url=BASE, transport=httpx2.MockTransport(_handler(seen)), default_rate_limit=fast).petstore.latest
    page = api.list_pets(limit=2, tags=["x"])
    assert [p.id for p in page] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert len(seen) == 4 and len(acquires) == 4
    assert all("tags=x" in str(r.url) for r in seen)  # params kept (no drop)

    async def go() -> list[int]:
        aseen: list[httpx2.Request] = []
        aapi = AsyncClient(base_url=BASE, transport=httpx2.MockTransport(_handler(aseen)), default_rate_limit=fast).petstore.latest
        p = await aapi.list_pets(limit=2)
        ids = [x.id async for x in p]
        assert len(aseen) == 4
        return ids

    assert asyncio.run(go()) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert len(acquires) == 8


def test_drop_params_on_next_keeps_path_and_keep_params() -> None:
    op = PetstoreV3._ops["list_pets"]
    desc = Pagination(
        items_path="items", next_token_path="nextToken", next_token_param="nextToken", drop_params_on_next=True, keep_params=("limit",)
    )
    p = compile_pagination(desc, op.query_params, op.path_params, op.header_params)
    assert p.next_kwargs({"limit": 2, "tags": ["a"], "status": "sold"}, "t9") == {"limit": 2, "next_token": "t9"}
    with pytest.raises(ValueError, match="not a query/header parameter"):
        compile_pagination(Pagination(items_path="items", next_token_path="n", next_token_param="nope"), op.query_params, (), ())


def test_prev_token_and_items_is_object() -> None:
    api = Client(
        base_url=BASE, transport=httpx2.MockTransport(lambda r: httpx2.Response(200, json={"items": [], "total": "prev"}))
    ).petstore.latest
    desc = Pagination(items_path="items", next_token_path="nextToken", next_token_param="nextToken", prev_token_path="total")
    page: Any = api.list_pets(paginate=desc, raw=True)
    assert page.prev_token == "prev" and page.items == [] and not page.has_next
    obj = Pagination(items_path="", next_token_path="nextToken", next_token_param="nextToken", items_is_object=True)
    page2: Any = api.list_pets(paginate=obj, raw=True)
    assert page2.items == [page2.raw]
