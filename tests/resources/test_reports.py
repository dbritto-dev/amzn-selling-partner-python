import gzip

import httpx2
import pytest

import amzn_selling_partner as sp
from amzn_selling_partner import _base_client
from tests.conftest import maybe_await

RESOURCE_PATH = "/reports/2021-06-30"


def report_json(report_id: str = "report-1") -> dict:
    return {
        "reportId": report_id,
        "reportType": "GET_VENDOR_INVENTORY_REPORT",
        "createdTime": "2023-01-01T00:00:00",
        "processingStatus": "DONE",
    }


def report_spec() -> sp.reports.CreateReportSpecification:
    return sp.reports.CreateReportSpecification(
        reportType=sp.reports.ReportType.VENDOR_INVENTORY_REPORT,
        marketplaceIds=[sp.reports.MarketPlaceId.UNITED_STATES_OF_AMERICA],
    )


async def test_create_report(client_factory):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST" and request.url.path == f"{RESOURCE_PATH}/reports":
            return httpx2.Response(200, json={"reportId": "report-1"})
        if request.method == "GET" and request.url.path == f"{RESOURCE_PATH}/reports/report-1":
            return httpx2.Response(200, json=report_json())
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = client_factory(handler)
    report = await maybe_await(client.reports.create_report(report_spec()))
    assert report.reportId == "report-1"
    assert report.processingStatus == sp.reports.ProcessingStatus.DONE


@pytest.mark.parametrize(
    ("pages_limit", "expected_ids", "expected_fetches"),
    [
        (1, ["report-1"], 1),
        (2, ["report-1", "report-2"], 2),
        (3, ["report-1", "report-2", "report-3"], 3),
        (10, ["report-1", "report-2", "report-3", "report-4"], 4),
    ],
)
async def test_get_reports_pagination_respects_pages_limit(
    client_factory, pages_limit, expected_ids, expected_fetches
):
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        n = calls["n"]
        body = {"reports": [report_json(f"report-{n}")]}
        if n < 4:
            body["nextToken"] = f"token-{n}"
        # Tiny rate-limit value keeps get_reports' proactive throttle sleep negligible here.
        return httpx2.Response(200, json=body, headers={"x-amzn-RateLimit-Limit": "0.001"})

    client = client_factory(handler)
    reports = await maybe_await(client.reports.get_reports(pages_limit=pages_limit))
    assert [r.reportId for r in reports] == expected_ids
    assert calls["n"] == expected_fetches


async def test_get_reports_sleeps_based_on_rate_limit_header(
    client_factory, client_kind, monkeypatch
):
    sleeps = []
    if client_kind == "sync":

        def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setattr(_base_client.time, "sleep", fake_sleep)
    else:

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setattr(_base_client.asyncio, "sleep", fake_sleep)

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, json={"reports": []}, headers={"x-amzn-RateLimit-Limit": "0.5"}
        )

    client = client_factory(handler)
    await maybe_await(client.reports.get_reports())
    assert sleeps == [50.0]


async def test_get_report_document_content_gzip_default(client_factory):
    doc_id = "doc-1"
    s3_url = "https://tortuga-prod-na.s3-external-1.amazonaws.com/doc-1"

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == f"{RESOURCE_PATH}/documents/{doc_id}":
            return httpx2.Response(
                200,
                json={
                    "reportDocumentId": doc_id,
                    "url": s3_url,
                    "compressionAlgorithm": "GZIP",
                },
            )
        if str(request.url) == s3_url:
            assert request.headers.get("x-amz-access-token") is None
            assert request.headers.get("authorization") is None
            return httpx2.Response(200, content=gzip.compress(b"{}"))
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = client_factory(handler)
    content = await maybe_await(client.reports.get_report_document_content(doc_id))
    assert content == {}


async def test_get_report_document_content_with_content_encoding_header(client_factory):
    doc_id = "doc-2"
    s3_url = "https://tortuga-prod-na.s3-external-1.amazonaws.com/doc-2"

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == f"{RESOURCE_PATH}/documents/{doc_id}":
            return httpx2.Response(
                200,
                json={
                    "reportDocumentId": doc_id,
                    "url": s3_url,
                    "compressionAlgorithm": "GZIP",
                },
            )
        if str(request.url) == s3_url:
            return httpx2.Response(
                200, content=gzip.compress(b"{}"), headers={"Content-Encoding": "gzip"}
            )
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = client_factory(handler)
    content = await maybe_await(client.reports.get_report_document_content(doc_id))
    assert content == {}


async def test_download_report_document_content(client_factory, tmp_path):
    doc_id = "doc-3"
    s3_url = "https://tortuga-prod-na.s3-external-1.amazonaws.com/doc-3"

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == f"{RESOURCE_PATH}/documents/{doc_id}":
            return httpx2.Response(
                200,
                json={
                    "reportDocumentId": doc_id,
                    "url": s3_url,
                    "compressionAlgorithm": "GZIP",
                },
            )
        if str(request.url) == s3_url:
            return httpx2.Response(200, content=gzip.compress(b'{"a": 1}'))
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = client_factory(handler)
    file_path = str(tmp_path / f"{doc_id}.json")
    await maybe_await(client.reports.download_report_document_content(doc_id, file_path))

    with open(file_path) as f:
        assert f.read() == '{"a": 1}'


async def test_retries_on_429_with_retry_after_then_succeeds(client_factory):
    attempts = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == f"{RESOURCE_PATH}/reports/report-1":
            attempts["n"] += 1
            if attempts["n"] == 1:
                return httpx2.Response(429, headers={"Retry-After": "0"}, json={})
            return httpx2.Response(200, json=report_json())
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    client = client_factory(handler, max_retries=2)
    report = await maybe_await(client.reports.get_report("report-1"))
    assert report.reportId == "report-1"
    assert attempts["n"] == 2


async def test_retries_exhausted_raises_rate_limit_error(client_factory):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(429, headers={"Retry-After": "0"}, json={"errors": []})

    client = client_factory(handler, max_retries=1)
    with pytest.raises(sp._exceptions.RateLimitError):
        await maybe_await(client.reports.get_report("report-1"))


async def test_5xx_maps_to_internal_server_error(client_factory):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(500, json={"errors": []})

    client = client_factory(handler, max_retries=0)
    with pytest.raises(sp._exceptions.InternalServerError):
        await maybe_await(client.reports.get_report("report-1"))


async def test_timeout_maps_to_api_timeout_error(client_factory):
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    client = client_factory(handler, max_retries=0)
    with pytest.raises(sp._exceptions.APITimeoutError):
        await maybe_await(client.reports.get_report("report-1"))


async def test_with_raw_response_create_report_returns_only_initial_response(client_factory):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            return httpx2.Response(200, json={"reportId": "report-1"})
        raise AssertionError("with_raw_response.create_report should not follow up with a GET")

    client = client_factory(handler)
    response = await maybe_await(client.reports.with_raw_response.create_report(report_spec()))
    assert isinstance(response, httpx2.Response)
    assert response.json() == {"reportId": "report-1"}


@pytest.mark.parametrize("bad_report_id", [None, 123])
async def test_get_report_rejects_invalid_report_id(client_factory, bad_report_id):
    client = client_factory(lambda request: httpx2.Response(200, json=report_json()))
    with pytest.raises(ValueError):
        await maybe_await(client.reports.get_report(bad_report_id))


async def test_download_report_document_content_rejects_invalid_file_path(client_factory):
    client = client_factory(lambda request: httpx2.Response(200, json={}))
    with pytest.raises(ValueError):
        await maybe_await(client.reports.download_report_document_content("doc-1", None))


@pytest.mark.parametrize("bad_document_id", [None, 123])
async def test_get_report_document_rejects_invalid_document_id(client_factory, bad_document_id):
    client = client_factory(lambda request: httpx2.Response(200, json={}))
    with pytest.raises(ValueError):
        await maybe_await(client.reports.get_report_document(bad_document_id))


@pytest.mark.parametrize("bad_document_id", [None, 123])
async def test_get_report_document_content_rejects_invalid_document_id(
    client_factory, bad_document_id
):
    client = client_factory(lambda request: httpx2.Response(200, json={}))
    with pytest.raises(ValueError):
        await maybe_await(client.reports.get_report_document_content(bad_document_id))


@pytest.mark.parametrize("bad_document_id", [None, 123])
async def test_download_report_document_content_rejects_invalid_document_id(
    client_factory, bad_document_id, tmp_path
):
    client = client_factory(lambda request: httpx2.Response(200, json={}))
    with pytest.raises(ValueError):
        await maybe_await(
            client.reports.download_report_document_content(
                bad_document_id, str(tmp_path / "out.json")
            )
        )


async def test_with_raw_response_get_reports(client_factory):
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"reports": [report_json()]})

    client = client_factory(handler)
    response = await maybe_await(client.reports.with_raw_response.get_reports())
    assert isinstance(response, httpx2.Response)
    assert response.json()["reports"][0]["reportId"] == "report-1"


async def test_with_raw_response_get_report(client_factory):
    client = client_factory(lambda request: httpx2.Response(200, json=report_json()))
    response = await maybe_await(client.reports.with_raw_response.get_report("report-1"))
    assert isinstance(response, httpx2.Response)
    assert response.json()["reportId"] == "report-1"


async def test_with_raw_response_get_report_document(client_factory):
    doc_id = "doc-1"

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json={
                "reportDocumentId": doc_id,
                "url": "https://tortuga-prod-na.s3-external-1.amazonaws.com/doc-1",
            },
        )

    client = client_factory(handler)
    response = await maybe_await(client.reports.with_raw_response.get_report_document(doc_id))
    assert isinstance(response, httpx2.Response)
    assert response.json()["reportDocumentId"] == doc_id
