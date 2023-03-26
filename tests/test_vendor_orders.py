import datetime
import gzip
import pathlib
import uuid

import pytest
import responses

import amzn_selling_partner as sp


@pytest.fixture(autouse=True)
def mock_datetime_utcnow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        datetime,
        "datetime",
        type(
            "MockDatetime",
            (datetime.datetime,),
            {"utcnow": classmethod(lambda _: datetime.datetime(2023, 1, 1))},
        ),
    )


@pytest.fixture(autouse=True)
def mock_client_session_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sp.client.auth,
        "ClientSessionAuth",
        type(
            "MockClientSessionAuth",
            (),
            {"__init__": lambda _, *__, **___: None, "__call__": lambda _, request: request},
        ),
    )


@pytest.fixture
def mock_purchase_order() -> sp.vendor.orders.Order:
    return sp.vendor.orders.Order(
        purchaseOrderNumber=f"purchase-order-{int(sp.utils.date.datetime_utcnow().timestamp())}",
        orderDetails=sp.vendor.orders.OrderDetails(
            purchaseOrderDate="",
            purchaseOrderType=sp.vendor.orders.PurchaseOrderType.REGULAR_ORDER,
            purchaseOrderStateChangedDate="",
            items=[],
        ),
        purchaseOrderState=sp.vendor.orders.PurchaseOrderState.CLOSED,
    )


@pytest.fixture(autouse=True)
def mock_responses(mock_purchase_order: sp.vendor.orders.Order) -> None:
    responses.get(
        "https://sellingpartnerapi-na.amazon.com/vendor/orders/v1/purchaseOrders",
        json={"payload": {"orders": [mock_purchase_order.dict(exclude_none=True)]}},
    )
    responses.get(
        f"https://sellingpartnerapi-na.amazon.com/vendor/orders/v1/purchaseOrders/{mock_purchase_order.purchaseOrderNumber}",
        json={"payload": mock_purchase_order.dict(exclude_none=True)},
    )


@pytest.fixture
def vendor_orders_client() -> sp.vendor.orders.Client:
    return sp.vendor.orders.Client()


def test_get_resource_path(vendor_orders_client: sp.vendor.orders.Client) -> None:
    assert "vendor/orders/v1" == vendor_orders_client.get_resource_path()


def test_get_resource_endpoint(vendor_orders_client: sp.vendor.orders.Client) -> None:
    assert (
        f"{sp.client.SellingPartnerRegion.NORTH_AMERICA.api_endpoint}/vendor/orders/v1"
        == vendor_orders_client.get_resource_endpoint()
    )


def test_get_operation_endpoint(vendor_orders_client: sp.vendor.orders.Client) -> None:
    assert (
        f"{sp.client.SellingPartnerRegion.NORTH_AMERICA.api_endpoint}/vendor/orders/v1/operationMethod"
        == vendor_orders_client.get_operation_endpoint("operationMethod")
    )


@responses.activate
def test_get_purchase_orders(
    vendor_orders_client: sp.vendor.orders.Client, mock_purchase_order: sp.vendor.orders.Order
):
    assert [mock_purchase_order] == vendor_orders_client.get_purchase_orders()


@responses.activate
def test_get_purchase_order(
    vendor_orders_client: sp.vendor.orders.Client, mock_purchase_order: sp.vendor.orders.Order
):
    assert mock_purchase_order == vendor_orders_client.get_purchase_order(
        mock_purchase_order.purchaseOrderNumber
    )
