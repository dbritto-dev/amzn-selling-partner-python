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
def mock_report() -> sp.reports.Report:
    return sp.reports.Report(
        reportId=f"report-document-{int(sp.utils.date.datetime_utcnow().timestamp())}",
        reportType=sp.reports.ReportType.VENDOR_INVENTORY_REPORT,
        processingStatus=sp.reports.ProcessingStatus.DONE,
        createdTime="2023-01-01T00:00:00",
    )


@pytest.fixture
def mock_report_document() -> sp.reports.ReportDocument:
    return sp.reports.ReportDocument(
        reportDocumentId=f"report-document-{int(sp.utils.date.datetime_utcnow().timestamp())}",
        url=f"https://tortuga-prod-na.s3-external-1.amazonaws.com/{uuid.uuid4().hex}",
    )


@pytest.fixture
def mock_report_document_content() -> bytes:
    return gzip.compress(b"{}")


@pytest.fixture(autouse=True)
def mock_responses(
    mock_report: sp.reports.Report,
    mock_report_document: sp.reports.ReportDocument,
    mock_report_document_content: bytes,
) -> None:
    responses.post(
        "https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports",
        json={"reportId": mock_report.reportId},
    )
    responses.get(
        "https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports",
        json={"reports": [mock_report.dict(exclude_none=True)]},
    )
    responses.get(
        f"https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports/{mock_report.reportId}",
        json=mock_report.dict(exclude_none=True),
    )
    responses.get(
        f"https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/documents/{mock_report_document.reportDocumentId}",
        json=mock_report_document.dict(exclude_none=True),
    )
    responses.get(mock_report_document.url, body=mock_report_document_content)


@pytest.fixture
def reports_client() -> sp.reports.Client:
    return sp.reports.Client()


def test_get_resource_path(reports_client: sp.reports.Client) -> None:
    assert "reports/2021-06-30" == reports_client.get_resource_path()


def test_get_resource_endpoint(reports_client: sp.reports.Client) -> None:
    assert (
        f"{sp.client.SellingPartnerRegion.NORTH_AMERICA.api_endpoint}/reports/2021-06-30"
        == reports_client.get_resource_endpoint()
    )


def test_get_operation_endpoint(reports_client: sp.reports.Client) -> None:
    assert (
        f"{sp.client.SellingPartnerRegion.NORTH_AMERICA.api_endpoint}/reports/2021-06-30/operationMethod"
        == reports_client.get_operation_endpoint("operationMethod")
    )


@responses.activate
def test_create_report(mock_report: sp.reports.Report) -> None:
    reports_client = sp.reports.Client()
    assert mock_report == reports_client.create_report(
        sp.reports.CreateReportSpecification(
            reportType=sp.reports.ReportType.VENDOR_SALES_REPORT,
            marketplaceIds=[sp.reports.MarketPlaceId.UNITED_STATES_OF_AMERICA],
            dataStartTime=sp.utils.date.amazon_isoformat(sp.utils.date.datetime_utcnow()),
        )
    )


@responses.activate
def test_get_reports(reports_client: sp.reports.Client, mock_report: sp.reports.Report) -> None:
    assert [mock_report] == reports_client.get_reports()


@responses.activate
def test_get_report(reports_client: sp.reports.Client, mock_report: sp.reports.Report) -> None:
    assert mock_report == reports_client.get_report(mock_report.reportId)


@responses.activate
def test_get_report_document(
    reports_client: sp.reports.Client, mock_report_document: sp.reports.ReportDocument
) -> None:
    assert mock_report_document == reports_client.get_report_document(
        mock_report_document.reportDocumentId
    )


@responses.activate
def test_get_report_document_content(
    reports_client: sp.reports.Client, mock_report_document: sp.reports.ReportDocument
) -> None:
    assert {} == reports_client.get_report_document_content(mock_report_document.reportDocumentId)


@responses.activate
def test_download_report_document_content(
    reports_client: sp.reports.Client,
    mock_report_document: sp.reports.ReportDocument,
    mock_report_document_content: bytes,
    tmp_path: pathlib.Path,
) -> None:
    file_path = str(tmp_path / f"{mock_report_document.reportDocumentId}.json")
    reports_client.download_report_document_content(
        mock_report_document.reportDocumentId, file_path
    )

    with open(file_path) as f:
        assert gzip.decompress(mock_report_document_content).decode() == f.read()
