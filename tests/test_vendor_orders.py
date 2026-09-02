import datetime
from decimal import Decimal

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


@pytest.fixture
def mock_next_purchase_order() -> sp.vendor.orders.Order:
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


def test_vendor_order_models_match_sp_api_types() -> None:
    money = sp.vendor.orders.Money(
        currencyCode="USD",
        amount="12.34",
        unitOfMeasure=sp.vendor.orders.MoneyUnitOfMeasure.POUNDS,
    )
    quantity = sp.vendor.orders.ItemQuantity(unitOfMeasure=sp.vendor.orders.UnitOfMeasure.CASES)
    address = sp.vendor.orders.Address(
        name="Name",
        addressLine1="Street",
        countryCode="US",
        county="County",
        district="District",
    )

    assert money.amount == Decimal("12.34")
    assert money.unitOfMeasure == sp.vendor.orders.MoneyUnitOfMeasure.POUNDS
    assert quantity.unitOfMeasure == sp.vendor.orders.UnitOfMeasure.CASES
    assert address.county == "County"
    assert address.district == "District"


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
def test_get_purchase_orders_with_next_page(
    vendor_orders_client: sp.vendor.orders.Client,
    mock_purchase_order: sp.vendor.orders.Order,
    mock_next_purchase_order: sp.vendor.orders.Order,
):
    mock_next_token = sp.utils.date.datetime_utcnow().timestamp().hex()
    responses.replace(
        responses.GET,
        "https://sellingpartnerapi-na.amazon.com/vendor/orders/v1/purchaseOrders",
        json={
            "payload": {
                "orders": [mock_purchase_order.dict(exclude_none=True)],
                "pagination": {"nextToken": mock_next_token},
            },
        },
    )
    responses.add(
        responses.GET,
        "https://sellingpartnerapi-na.amazon.com/vendor/orders/v1/purchaseOrders",
        json={"payload": {"orders": [mock_next_purchase_order.dict(exclude_none=True)]}},
    )

    assert [
        mock_purchase_order,
        mock_next_purchase_order,
    ] == vendor_orders_client.get_purchase_orders()


@responses.activate
def test_get_purchase_orders_no_payload(vendor_orders_client: sp.vendor.orders.Client):
    responses.replace(
        responses.GET,
        "https://sellingpartnerapi-na.amazon.com/vendor/orders/v1/purchaseOrders",
        json={"payload": None},
    )

    assert [] == vendor_orders_client.get_purchase_orders()


@responses.activate
def test_get_purchase_orders_no_orders(vendor_orders_client: sp.vendor.orders.Client):
    responses.replace(
        responses.GET,
        "https://sellingpartnerapi-na.amazon.com/vendor/orders/v1/purchaseOrders",
        json={"payload": {"orders": None}},
    )

    assert [] == vendor_orders_client.get_purchase_orders()


@responses.activate
def test_get_purchase_order(
    vendor_orders_client: sp.vendor.orders.Client, mock_purchase_order: sp.vendor.orders.Order
):
    assert mock_purchase_order == vendor_orders_client.get_purchase_order(
        mock_purchase_order.purchaseOrderNumber
    )


@responses.activate
def test_get_purchase_order_none_purchase_order_number(
    vendor_orders_client: sp.vendor.orders.Client,
):
    with pytest.raises(ValueError):
        vendor_orders_client.get_purchase_order(None)  # type: ignore


@responses.activate
def test_get_purchase_order_non_string_purchase_order_number(
    vendor_orders_client: sp.vendor.orders.Client,
):
    with pytest.raises(ValueError):
        vendor_orders_client.get_purchase_order(
            sp.utils.date.datetime_utcnow().timestamp()  # type: ignore
        )
