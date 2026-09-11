"""The 0.1.x ``amzn_selling_partner`` entry points keep working on top of amzn_selling_partner."""

from __future__ import annotations

import gzip
import json
import pathlib
import warnings

import httpx2
import pytest

import amzn_selling_partner as sp
from amzn_selling_partner import client as compat_client

from .conftest import requires_amazon

pytestmark = requires_amazon


class VendorMock:
    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/auth/o2/token"):
            return httpx2.Response(200, json={"access_token": "tok", "expires_in": 3600})
        if path == "/vendor/orders/v1/purchaseOrders":
            if request.url.params.get("nextToken") == "n2":
                return httpx2.Response(200, json={"payload": {"orders": [{"purchaseOrderNumber": "PO-2", "purchaseOrderState": "Closed"}]}})
            return httpx2.Response(
                200,
                json={
                    "payload": {"pagination": {"nextToken": "n2"}, "orders": [{"purchaseOrderNumber": "PO-1", "purchaseOrderState": "New"}]}
                },
            )
        if path == "/vendor/orders/v1/purchaseOrders/PO-1":
            return httpx2.Response(
                200,
                json={
                    "payload": {
                        "purchaseOrderNumber": "PO-1",
                        "purchaseOrderState": "New",
                        "orderDetails": {
                            "purchaseOrderDate": "2020-01-01T00:00:00Z",
                            "purchaseOrderStateChangedDate": "2020-01-01T00:00:00Z",
                            "purchaseOrderType": "RegularOrder",
                            "items": [],
                        },
                    }
                },
            )
        if path == "/reports/2021-06-30/reports" and request.method == "POST":
            return httpx2.Response(202, json={"reportId": "R1"})
        if path == "/reports/2021-06-30/reports":
            token = request.url.params.get("nextToken")
            n = int(token[1:]) if token else 1
            return httpx2.Response(
                200,
                json={
                    "reports": [
                        {
                            "reportId": f"R{n}",
                            "reportType": "GET_VENDOR_SALES_REPORT",
                            "createdTime": "2020-01-01T00:00:00Z",
                            "processingStatus": "DONE",
                        }
                    ],
                    "nextToken": f"n{n + 1}",
                },
            )
        if path == "/reports/2021-06-30/reports/R1":
            return httpx2.Response(
                200,
                json={
                    "reportId": "R1",
                    "reportType": "GET_VENDOR_SALES_REPORT",
                    "createdTime": "2020-01-01T00:00:00Z",
                    "processingStatus": "DONE",
                    "reportDocumentId": "D1",
                },
            )
        if path == "/reports/2021-06-30/documents/D1":
            return httpx2.Response(200, json={"reportDocumentId": "D1", "url": "https://s3.example/d1.gz", "compressionAlgorithm": "GZIP"})
        if path == "/d1.gz":
            return httpx2.Response(200, content=gzip.compress(json.dumps({"salesByAsin": []}).encode()))
        return httpx2.Response(404, json={"errors": [{"code": "NotFound", "message": path}]})


def _kw(mock: VendorMock) -> dict[str, object]:
    return {
        "transport": httpx2.MockTransport(mock),
        "throttle": False,
        "selling_partner_app_client_id": "id",
        "selling_partner_app_client_secret": "sec",
        "selling_partner_app_refresh_token": "rt",
    }


def test_region_and_base_client_endpoints() -> None:
    assert sp.client.SellingPartnerRegion.NORTH_AMERICA.api_endpoint == "https://sellingpartnerapi-na.amazon.com"
    assert sp.client.SellingPartnerRegion.EUROPE.api_sandbox_endpoint == "https://sandbox.sellingpartnerapi-eu.amazon.com"
    assert sp.client.SellingPartnerRegion.FAR_EAST.region_name == "us-west-2"
    base = compat_client.BaseClient(transport=httpx2.MockTransport(VendorMock()))
    assert base.get_api_endpoint() == "https://sellingpartnerapi-na.amazon.com"
    with pytest.raises(NotImplementedError):
        base.get_resource_endpoint()
    sandbox = compat_client.BaseClient(sandbox=True, transport=httpx2.MockTransport(VendorMock()))
    assert sandbox.get_api_endpoint().startswith("https://sandbox.")


def test_aws_arguments_are_ignored_with_a_warning() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        compat_client.BaseClient(aws_access_key_id="AKIA", aws_secret_access_key="x", transport=httpx2.MockTransport(VendorMock()))
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    with pytest.raises(NotImplementedError):
        sp.client.auth.ClientSessionAuth()


def test_vendor_orders_client() -> None:
    mock = VendorMock()
    client = sp.vendor.orders.Client(**_kw(mock))
    assert client.get_resource_path() == "vendor/orders/v1"
    assert client.get_operation_endpoint("purchaseOrders") == "https://sellingpartnerapi-na.amazon.com/vendor/orders/v1/purchaseOrders"
    orders = client.get_purchase_orders(
        query=sp.vendor.orders.GetPurchaseOrdersQuery(createdAfter="2020-01-01T00:00:00Z", sortOrder=sp.vendor.orders.SortOrder.ASCENDING)
    )
    assert [o.purchase_order_number for o in orders] == ["PO-1", "PO-2"]  # auto-paged
    first = [r for r in mock.requests if r.url.path.endswith("/purchaseOrders")][0]
    assert first.url.params["createdAfter"] == "2020-01-01T00:00:00Z" and first.url.params["sortOrder"] == "ASC"
    order = client.get_purchase_order("PO-1")
    assert order.purchase_order_number == "PO-1" and order.order_details.purchase_order_type == "RegularOrder"
    assert isinstance(order, sp.vendor.orders.Order)
    assert sp.vendor.orders.PurchaseOrderState.CLOSED == "Closed"
    with pytest.raises(ValueError):
        client.get_purchase_order("")
    assert mock.requests[0].url.path.endswith("/auth/o2/token")
    assert [r for r in mock.requests if r.url.path.endswith("/purchaseOrders")][0].headers["x-amz-access-token"] == "tok"


def test_reports_client(tmp_path: pathlib.Path) -> None:
    mock = VendorMock()
    client = sp.reports.Client(**_kw(mock))
    report = client.create_report(
        sp.reports.CreateReportSpecification(
            reportType=sp.reports.ReportType.VENDOR_SALES_REPORT, marketplaceIds=[sp.reports.MarketPlaceId.UNITED_STATES_OF_AMERICA]
        )
    )
    assert report.report_id == "R1" and report.report_document_id == "D1"
    create = [r for r in mock.requests if r.method == "POST" and r.url.path.endswith("/reports")][0]
    assert json.loads(create.content) == {"reportType": "GET_VENDOR_SALES_REPORT", "marketplaceIds": ["ATVPDKIKX0DER"]}
    reports = client.get_reports(query=sp.reports.GetReportsQuery(reportTypes=[sp.reports.ReportType.VENDOR_SALES_REPORT]), pages_limit=2)
    assert [r.report_id for r in reports] == ["R1", "R2"]
    doc = client.get_report_document("D1")
    assert doc.url.endswith("/d1.gz") and doc.compression_algorithm == "GZIP"
    assert client.get_report_document_content("D1") == {"salesByAsin": []}
    target = tmp_path / "out.json"
    client.download_report_document_content("D1", str(target))
    assert json.loads(target.read_bytes()) == {"salesByAsin": []}
    with pytest.raises(ValueError):
        client.get_report("")
    assert sp.reports.Report is client.api.models.Report
    assert isinstance(client.get_report("R1"), sp.reports.Report)


def test_utils_kept() -> None:
    assert sp.utils.date.amazon_isoformat(sp.utils.date.datetime_utcnow()).endswith("Z")
    assert callable(sp.utils.file.write_binary_file)
