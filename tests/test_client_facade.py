import typing

import pytest

import amzn_selling_partner as sp
from tests.conftest import CLIENT_KWARGS

_ASYNC_TO_SYNC_NAME = {"aclose": "close"}


def public_attrs(cls: type) -> typing.Set[str]:
    return {name for name in dir(cls) if not name.startswith("_")}


def normalized_client_attrs(cls: type, *, is_async: bool) -> typing.Set[str]:
    names = public_attrs(cls)
    if is_async:
        names = {_ASYNC_TO_SYNC_NAME.get(name, name) for name in names}
    return names


def test_client_and_async_client_have_matching_public_surface() -> None:
    assert normalized_client_attrs(sp.Client, is_async=False) == normalized_client_attrs(
        sp.AsyncClient, is_async=True
    )


def test_reports_and_async_reports_have_matching_public_surface() -> None:
    assert public_attrs(sp.reports.Reports) == public_attrs(sp.reports.AsyncReports)


def test_orders_and_async_orders_have_matching_public_surface() -> None:
    assert public_attrs(sp.vendor.orders.Orders) == public_attrs(sp.vendor.orders.AsyncOrders)


def test_base_client_shim_warns_on_construction() -> None:
    with pytest.warns(DeprecationWarning):
        sp.client.BaseClient()


def test_reports_client_shim_warns_and_preserves_public_methods() -> None:
    with pytest.warns(DeprecationWarning):
        client = sp.reports.Client(**CLIENT_KWARGS)

    for method in (
        "create_report",
        "get_reports",
        "get_report",
        "get_report_document",
        "get_report_document_content",
        "download_report_document_content",
    ):
        assert callable(getattr(client, method))


def test_reports_client_shim_preserves_endpoint_helpers() -> None:
    with pytest.warns(DeprecationWarning):
        client = sp.reports.Client(**CLIENT_KWARGS)

    assert client.get_resource_path() == "reports/2021-06-30"
    assert (
        client.get_resource_endpoint()
        == "https://sellingpartnerapi-na.amazon.com/reports/2021-06-30"
    )
    assert (
        client.get_operation_endpoint("x")
        == "https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/x"
    )


def test_vendor_orders_client_shim_warns_and_preserves_public_methods() -> None:
    with pytest.warns(DeprecationWarning):
        client = sp.vendor.orders.Client(**CLIENT_KWARGS)

    for method in ("get_purchase_orders", "get_purchase_order"):
        assert callable(getattr(client, method))

    assert client.get_resource_path() == "vendor/orders/v1"
    assert (
        client.get_resource_endpoint()
        == "https://sellingpartnerapi-na.amazon.com/vendor/orders/v1"
    )
    assert (
        client.get_operation_endpoint("x")
        == "https://sellingpartnerapi-na.amazon.com/vendor/orders/v1/x"
    )
