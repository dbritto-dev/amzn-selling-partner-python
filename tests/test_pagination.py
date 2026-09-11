from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx2
import pytest

from spapi.client import AsyncClient, Client
from spapi.compile.models import build_models
from spapi.compile.operations import compile_operations, detect_pagination
from spapi.runtime import Pagination, RateLimit
from spapi.runtime._throttle import AsyncTokenBucket, TokenBucket
from spapi.spec import Document, load_document

from .conftest import LISTINGS_ITEMS, OAS31, ORDERS_V0, SWAGGER2, requires_amazon

EXPECTED = {
    OAS31.name: {"listPets": ("items", "nextToken", "nextToken")},
    SWAGGER2.name: {
        "listPets": ("payload.Pets", "payload.NextToken", "NextToken"),
        "getOrders": ("payload.orders", "payload.pagination.nextToken", "NextToken"),
    },
}
EXPECTED_AMAZON = {
    ORDERS_V0.name: {"getOrders": "payload.Orders", "getOrderItems": "payload.OrderItems", "getOrderItemsBuyerInfo": "payload.OrderItems"},
    LISTINGS_ITEMS.name: {"searchListingsItems": "items"},
}


@pytest.mark.parametrize("spec", [OAS31, SWAGGER2])
def test_detection_matches_expected_list(spec: Any) -> None:
    doc = load_document(spec)
    detected = {op.operation_id: detect_pagination(op, doc) for op in doc.operations}
    found = {k: (v.items_path, v.next_token_path, v.next_token_param) for k, v in detected.items() if v is not None}
    assert found == EXPECTED[spec.name]
    assert all(v.source == "heuristic" for v in detected.values() if v is not None)


@requires_amazon
@pytest.mark.parametrize("spec", [ORDERS_V0, LISTINGS_ITEMS])
def test_detection_amazon(spec: Any) -> None:
    doc = load_document(spec)
    found = {op.operation_id: p.items_path for op in doc.operations if (p := detect_pagination(op, doc)) is not None}
    assert found == EXPECTED_AMAZON[spec.name]


class _RatePlugin:
    """Annotates every operation with a fast rate limit (for throttle tests)."""

    def annotate(self, document: Document) -> Document:
        return document.map_operations(lambda op: op.annotated(rate_limit=RateLimit(rate=1000, burst=2)))


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
    api = Client(OAS31, transport=httpx2.MockTransport(_handler(seen)), plugins=[_RatePlugin()]).petstore_oas31.latest
    page = api.list_pets(limit=2, tags=["x"])
    assert [p.id for p in page] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert len(seen) == 4 and len(acquires) == 4
    assert all("tags=x" in str(r.url) for r in seen)  # params kept (no drop)

    async def go() -> list[int]:
        aseen: list[httpx2.Request] = []
        aapi = AsyncClient(OAS31, transport=httpx2.MockTransport(_handler(aseen)), plugins=[_RatePlugin()]).petstore_oas31.latest
        p = await aapi.list_pets(limit=2)
        ids = [x.id async for x in p]
        assert len(aseen) == 4
        return ids

    assert asyncio.run(go()) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert len(acquires) == 8


def test_drop_params_on_next_keeps_path_and_keep_params() -> None:
    doc = load_document(OAS31)
    desc = Pagination(
        items_path="items", next_token_path="nextToken", next_token_param="nextToken", drop_params_on_next=True, keep_params=("limit",)
    )
    doc2 = doc.with_operations(tuple(op.annotated(pagination=desc) if op.operation_id == "listPets" else op for op in doc.operations))
    ops = {op.name: op for op in compile_operations(doc2, build_models(doc2, key="drop"), key_prefix="d")}
    p = ops["list_pets"].pagination
    assert p is not None
    assert p.next_kwargs({"limit": 2, "tags": ["a"], "status": "sold"}, "t9") == {"limit": 2, "next_token": "t9"}


def test_prev_token_and_items_is_object() -> None:
    doc = load_document(OAS31)
    desc = Pagination(items_path="items", next_token_path="nextToken", next_token_param="nextToken", prev_token_path="total")
    doc2 = doc.with_operations(tuple(op.annotated(pagination=desc) if op.operation_id == "listPets" else op for op in doc.operations))
    api = Client(
        doc2.source,
        transport=httpx2.MockTransport(lambda r: httpx2.Response(200, json={"items": [], "total": "prev"})),
        plugins=[type("P", (), {"annotate": staticmethod(lambda d: doc2)})()],
    ).petstore_oas31.latest
    page = api.list_pets(raw=True)
    assert page.prev_token == "prev" and page.items == [] and not page.has_next
    obj = Pagination(items_path="", next_token_path="nextToken", next_token_param="nextToken", items_is_object=True)
    page2 = api.list_pets(paginate=obj, raw=True)
    assert page2.items == [page2.raw]
