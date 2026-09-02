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
def mock_next_report() -> sp.reports.Report:
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
        compressionAlgorithm=sp.reports.CompressionAlgorithm.GZIP,
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
def test_create_report(reports_client: sp.reports.Client, mock_report: sp.reports.Report) -> None:
    assert mock_report == reports_client.create_report(
        sp.reports.CreateReportSpecification(
            reportType=sp.reports.ReportType.VENDOR_SALES_REPORT,
            marketplaceIds=[sp.reports.MarketPlaceId.UNITED_STATES_OF_AMERICA],
            dataStartTime=sp.utils.date.amazon_isoformat(sp.utils.date.datetime_utcnow()),
        )
    )


def test_report_models_accept_documented_values() -> None:
    report_options = sp.reports.ReportOptions(reportPeriod="DAY")
    specification = sp.reports.CreateReportSpecification(
        reportType=sp.reports.ReportType.VENDOR_INVENTORY_REPORT,
        marketplaceIds=[sp.reports.MarketPlaceId.UNITED_STATES_OF_AMERICA],
        reportOptions=report_options,
    )
    query = sp.reports.GetReportsQuery(
        reportTypes=[sp.reports.ReportType.VENDOR_INVENTORY_REPORT],
        marketplaceIds=[sp.reports.MarketPlaceId.UNITED_STATES_OF_AMERICA],
    )

    assert specification.dict()["reportOptions"] == {
        "reportPeriod": sp.reports.ReportPeriod.DAY,
        "distributorView": None,
        "sellingProgram": None,
    }
    assert query.reportTypes == [sp.reports.ReportType.VENDOR_INVENTORY_REPORT]


def test_report_models_reject_undocumented_values() -> None:
    with pytest.raises(ValueError):
        sp.reports.CreateReportSpecification(
            reportType="FEE_DISCOUNTS_REPORT",
            marketplaceIds=[sp.reports.MarketPlaceId.UNITED_STATES_OF_AMERICA],
        )

    with pytest.raises(ValueError):
        sp.reports.ReportOptions(customOption="value")


def test_marketplace_id_spain_alias_is_backwards_compatible() -> None:
    assert sp.reports.MarketPlaceId.SPAIN == sp.reports.MarketPlaceId.PAIN


@responses.activate
def test_get_reports(reports_client: sp.reports.Client, mock_report: sp.reports.Report) -> None:
    assert [mock_report] == reports_client.get_reports()


@responses.activate
def test_get_reports_with_next_page(
    reports_client: sp.reports.Client,
    mock_report: sp.reports.Report,
    mock_next_report: sp.reports.Report,
) -> None:
    mock_next_token = sp.utils.date.datetime_utcnow().timestamp().hex()

    responses.replace(
        responses.GET,
        "https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports",
        json={"reports": [mock_report.dict(exclude_none=True)], "nextToken": mock_next_token},
    )
    responses.add(
        responses.GET,
        "https://sellingpartnerapi-na.amazon.com/reports/2021-06-30/reports",
        json={"reports": [mock_next_report.dict(exclude_none=True)]},
    )

    assert [mock_report, mock_next_report] == reports_client.get_reports()


@responses.activate
def test_get_report(reports_client: sp.reports.Client, mock_report: sp.reports.Report) -> None:
    assert mock_report == reports_client.get_report(mock_report.reportId)


@responses.activate
def test_get_report_none_report_id(reports_client: sp.reports.Client) -> None:
    with pytest.raises(ValueError):
        reports_client.get_report(None)  # type: ignore


@responses.activate
def test_get_report_non_string_report_id(reports_client: sp.reports.Client) -> None:
    with pytest.raises(ValueError):
        reports_client.get_report(int(sp.utils.date.datetime_utcnow().timestamp()))  # type: ignore


@responses.activate
def test_get_report_document(
    reports_client: sp.reports.Client, mock_report_document: sp.reports.ReportDocument
) -> None:
    assert mock_report_document == reports_client.get_report_document(
        mock_report_document.reportDocumentId
    )


@responses.activate
def test_get_report_document_with_content_encoding_header(
    reports_client: sp.reports.Client, mock_report_document: sp.reports.ReportDocument
) -> None:
    assert mock_report_document == reports_client.get_report_document(
        mock_report_document.reportDocumentId,
        enable_content_encoding_url_header=True,
    )
    assert "enableContentEncodingUrlHeader=true" in responses.calls[-1].request.url


@responses.activate
def test_get_report_document_content_with_content_encoding_header(
    reports_client: sp.reports.Client, mock_report_document: sp.reports.ReportDocument
) -> None:
    responses.replace(
        responses.GET,
        mock_report_document.url,
        body=gzip.compress(b"{}"),
        headers={"Content-Encoding": "gzip"},
    )

    assert {} == reports_client.get_report_document_content(
        mock_report_document.reportDocumentId,
        enable_content_encoding_url_header=True,
    )


@responses.activate
def test_get_report_document_none_report_document_id(reports_client: sp.reports.Client) -> None:
    with pytest.raises(ValueError):
        reports_client.get_report_document(None)  # type: ignore


@responses.activate
def test_get_report_document_non_string_report_document_id(
    reports_client: sp.reports.Client,
) -> None:
    with pytest.raises(ValueError):
        reports_client.get_report_document(
            int(sp.utils.date.datetime_utcnow().timestamp())  # type: ignore
        )


@responses.activate
def test_get_report_document_content(
    reports_client: sp.reports.Client, mock_report_document: sp.reports.ReportDocument
) -> None:
    assert {} == reports_client.get_report_document_content(mock_report_document.reportDocumentId)


@responses.activate
def test_get_report_document_content_none_report_document_id(
    reports_client: sp.reports.Client,
) -> None:
    with pytest.raises(ValueError):
        reports_client.get_report_document_content(None)  # type: ignore


@responses.activate
def test_get_report_document_content_non_string_report_document_id(
    reports_client: sp.reports.Client,
) -> None:
    with pytest.raises(ValueError):
        reports_client.get_report_document_content(
            int(sp.utils.date.datetime_utcnow().timestamp())  # type: ignore
        )


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


@responses.activate
def test_download_report_document_content_none_report_document_id(
    reports_client: sp.reports.Client,
    mock_report_document: sp.reports.ReportDocument,
    tmp_path: pathlib.Path,
) -> None:
    file_path = str(tmp_path / f"{mock_report_document.reportDocumentId}.json")

    with pytest.raises(ValueError):
        reports_client.download_report_document_content(None, file_path)  # type: ignore


@responses.activate
def test_download_report_document_content_non_string_report_document_id(
    reports_client: sp.reports.Client,
    mock_report_document: sp.reports.ReportDocument,
    tmp_path: pathlib.Path,
) -> None:
    file_path = str(tmp_path / f"{mock_report_document.reportDocumentId}.json")

    with pytest.raises(ValueError):
        reports_client.download_report_document_content(
            int(sp.utils.date.datetime_utcnow().timestamp()), file_path  # type: ignore
        )


@responses.activate
def test_download_report_document_content_none_file_path(
    reports_client: sp.reports.Client,
    mock_report_document: sp.reports.ReportDocument,
) -> None:
    with pytest.raises(ValueError):
        reports_client.download_report_document_content(
            mock_report_document.reportDocumentId, None  # type: ignore
        )


@responses.activate
def test_download_report_document_content_non_string_file_path(
    reports_client: sp.reports.Client,
    mock_report_document: sp.reports.ReportDocument,
) -> None:
    with pytest.raises(ValueError):
        reports_client.download_report_document_content(
            mock_report_document.reportDocumentId, int(sp.utils.date.datetime_utcnow().timestamp())  # type: ignore
        )
