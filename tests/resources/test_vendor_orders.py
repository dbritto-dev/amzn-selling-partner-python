import httpx2
import pytest

from tests.conftest import maybe_await

RESOURCE_PATH = "/vendor/orders/v1"


def order_json(purchase_order_number: str = "po-1") -> dict:
    return {
        "purchaseOrderNumber": purchase_order_number,
        "purchaseOrderState": "Closed",
    }


async def test_get_purchase_orders_single_page(client_factory):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"payload": {"orders": [order_json()]}})

    client = client_factory(handler)
    orders = await maybe_await(client.vendor.orders.get_purchase_orders())
    assert [o.purchaseOrderNumber for o in orders] == ["po-1"]


async def test_get_purchase_orders_follows_pagination(client_factory):
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        n = calls["n"]
        body: dict = {"payload": {"orders": [order_json(f"po-{n}")]}}
        if n < 3:
            body["payload"]["pagination"] = {"nextToken": f"token-{n}"}
        return httpx2.Response(200, json=body)

    client = client_factory(handler)
    orders = await maybe_await(client.vendor.orders.get_purchase_orders())
    assert [o.purchaseOrderNumber for o in orders] == ["po-1", "po-2", "po-3"]
    assert calls["n"] == 3


async def test_get_purchase_orders_pagination_does_not_mutate_caller_query(client_factory):
    import amzn_selling_partner as sp

    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        n = calls["n"]
        body: dict = {"payload": {"orders": [order_json(f"po-{n}")]}}
        if n < 2:
            body["payload"]["pagination"] = {"nextToken": f"token-{n}"}
        return httpx2.Response(200, json=body)

    client = client_factory(handler)
    query = sp.vendor.orders.GetPurchaseOrdersQuery(limit=5)
    await maybe_await(client.vendor.orders.get_purchase_orders(query=query))
    assert query.nextToken is None
    assert query.limit == 5


async def test_get_purchase_orders_no_payload_returns_empty_list(client_factory):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"payload": None})

    client = client_factory(handler)
    assert await maybe_await(client.vendor.orders.get_purchase_orders()) == []


async def test_get_purchase_orders_no_orders_returns_empty_list(client_factory):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"payload": {"orders": None}})

    client = client_factory(handler)
    assert await maybe_await(client.vendor.orders.get_purchase_orders()) == []


async def test_get_purchase_order(client_factory):
    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.path == f"{RESOURCE_PATH}/purchaseOrders/po-1"
        return httpx2.Response(200, json={"payload": order_json()})

    client = client_factory(handler)
    order = await maybe_await(client.vendor.orders.get_purchase_order("po-1"))
    assert order.purchaseOrderNumber == "po-1"


@pytest.mark.parametrize("bad_value", [None, 123])
async def test_get_purchase_order_rejects_invalid_purchase_order_number(client_factory, bad_value):
    client = client_factory(lambda request: httpx2.Response(200, json={"payload": None}))
    with pytest.raises(ValueError):
        await maybe_await(client.vendor.orders.get_purchase_order(bad_value))


async def test_with_raw_response_get_purchase_order(client_factory):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"payload": order_json()})

    client = client_factory(handler)
    response = await maybe_await(client.vendor.orders.with_raw_response.get_purchase_order("po-1"))
    assert isinstance(response, httpx2.Response)
    assert response.json()["payload"]["purchaseOrderNumber"] == "po-1"


async def test_with_raw_response_get_purchase_orders(client_factory):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"payload": {"orders": [order_json()]}})

    client = client_factory(handler)
    response = await maybe_await(client.vendor.orders.with_raw_response.get_purchase_orders())
    assert isinstance(response, httpx2.Response)
    assert response.json()["payload"]["orders"][0]["purchaseOrderNumber"] == "po-1"
