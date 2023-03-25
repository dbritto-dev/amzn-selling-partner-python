import datetime
import random

import pytest
import responses

import amzn_selling_partner as sp


@pytest.fixture(autouse=True)
def mock_datetime_utcnow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        datetime,
        "datetime",
        type(
            "mockdatetime",
            (datetime.datetime,),
            {"utcnow": classmethod(lambda _: datetime.datetime(2023, 1, 1))},
        ),
    )


@pytest.fixture(autouse=True)
def mock_client_session_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sp.client,
        "ClientSessionAuth",
        type(
            "MockClientSessionAuth",
            (),
            {"__init__": lambda _, *__, **___: None, "__call__": lambda _, request: request},
        ),
    )


@pytest.fixture(autouse=True)
def mock_responses():
    mock_report_id = "1679772266"
    responses.post(
        "https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports",
        json={"reportId": mock_report_id},
    )
    responses.get(
        f"https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports/{mock_report_id}",
        json={
            "reportId": mock_report_id,
            "reportType": sp.reports.ReportType.VENDOR_INVENTORY_REPORT,
            "createdTime": sp.utils.date.datetime_utcnow().isoformat(),
            "processingStatus": sp.reports.ProcessingStatus.DONE,
        },
    )


@pytest.fixture
def reports_client() -> sp.reports.Client:
    return sp.reports.Client()


def test_reports_client_get_resource_path(reports_client: sp.reports.Client) -> None:
    assert "reports/2021-06-30" == reports_client.get_resource_path()


def test_reports_client_get_resource_endpoint(reports_client: sp.reports.Client) -> None:
    assert (
        f"{sp.client.SellingPartnerRegion.NORTH_AMERICA.api_endpoint}/reports/2021-06-30"
        == reports_client.get_resource_endpoint()
    )


def test_reports_client_get_operation_endpoint(reports_client: sp.reports.Client) -> None:
    assert (
        f"{sp.client.SellingPartnerRegion.NORTH_AMERICA.api_endpoint}/reports/2021-06-30/operationMethod"
        == reports_client.get_operation_endpoint("operationMethod")
    )


@responses.activate
def test__(reports_client: sp.reports.Client) -> None:
    assert {
        "reportType": sp.reports.ReportType.VENDOR_INVENTORY_REPORT,
        "reportId": "1679772266",
        "processingStatus": sp.reports.ProcessingStatus.DONE,
        "createdTime": "2023-01-01T00:00:00",
    } == reports_client.create_report(
        sp.reports.CreateReportSpecification(
            reportType=sp.reports.ReportType.VENDOR_SALES_REPORT,
            marketplaceIds=[sp.reports.MarketPlaceId.UNITED_STATES_OF_AMERICA],
            dataStartTime=sp.utils.date.amazon_isoformat(sp.utils.date.datetime_utcnow()),
        )
    ).dict(
        exclude_none=True
    )
