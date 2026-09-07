import asyncio
import datetime
import email.utils

import httpx2
import pytest

import amzn_selling_partner as sp
from amzn_selling_partner import _base_client
from tests.conftest import CLIENT_KWARGS, maybe_await
from tests.test_auth import _report_handler, report_json


def make_raw_client(client_kind: str, handler) -> "sp.Client | sp.AsyncClient":
    transport = httpx2.MockTransport(handler)
    cls = sp.Client if client_kind == "sync" else sp.AsyncClient
    return cls(transport=transport, max_retries=0, **CLIENT_KWARGS)


async def test_retries_on_connect_error_then_succeeds(client_kind):
    attempts = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/reports/report-1"):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise httpx2.ConnectError("boom", request=request)
            return httpx2.Response(200, json=report_json())
        return _report_handler(request)

    transport = httpx2.MockTransport(handler)
    cls = sp.Client if client_kind == "sync" else sp.AsyncClient
    client = cls(transport=transport, max_retries=1, **CLIENT_KWARGS)

    report = await maybe_await(client.reports.get_report("report-1"))
    assert report.reportId == "report-1"
    assert attempts["n"] == 2


async def test_connect_error_exhausted_raises_api_connection_error(client_kind):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/reports/report-1"):
            raise httpx2.ConnectError("boom", request=request)
        return _report_handler(request)

    client = make_raw_client(client_kind, handler)
    with pytest.raises(sp._exceptions.APIConnectionError):
        await maybe_await(client.reports.get_report("report-1"))


async def test_retry_backoff_without_retry_after_header(client_kind, monkeypatch):
    sleeps = []
    if client_kind == "sync":
        monkeypatch.setattr(_base_client.time, "sleep", lambda s: sleeps.append(s))
    else:

        async def fake_sleep(s: float) -> None:
            sleeps.append(s)

        monkeypatch.setattr(_base_client.asyncio, "sleep", fake_sleep)

    attempts = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/reports/report-1"):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return httpx2.Response(500, json={})
            return httpx2.Response(200, json=report_json())
        return _report_handler(request)

    transport = httpx2.MockTransport(handler)
    cls = sp.Client if client_kind == "sync" else sp.AsyncClient
    client = cls(transport=transport, max_retries=1, **CLIENT_KWARGS)

    report = await maybe_await(client.reports.get_report("report-1"))
    assert report.reportId == "report-1"
    assert len(sleeps) == 1
    assert sleeps[0] >= 0.0


async def test_retry_after_http_date_header(client_kind):
    retry_after_date = email.utils.format_datetime(datetime.datetime.now(datetime.timezone.utc))
    attempts = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/reports/report-1"):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return httpx2.Response(429, headers={"Retry-After": retry_after_date}, json={})
            return httpx2.Response(200, json=report_json())
        return _report_handler(request)

    transport = httpx2.MockTransport(handler)
    cls = sp.Client if client_kind == "sync" else sp.AsyncClient
    client = cls(transport=transport, max_retries=1, **CLIENT_KWARGS)

    report = await maybe_await(client.reports.get_report("report-1"))
    assert report.reportId == "report-1"


async def test_retry_after_unparseable_falls_back_to_jitter(client_kind):
    attempts = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/reports/report-1"):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return httpx2.Response(429, headers={"Retry-After": "not-a-valid-value"}, json={})
            return httpx2.Response(200, json=report_json())
        return _report_handler(request)

    transport = httpx2.MockTransport(handler)
    cls = sp.Client if client_kind == "sync" else sp.AsyncClient
    client = cls(transport=transport, max_retries=1, **CLIENT_KWARGS)

    report = await maybe_await(client.reports.get_report("report-1"))
    assert report.reportId == "report-1"


async def test_status_error_falls_back_to_text_body_on_invalid_json(client_kind):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/reports/report-1"):
            return httpx2.Response(404, content=b"not json")
        return _report_handler(request)

    client = make_raw_client(client_kind, handler)
    with pytest.raises(sp._exceptions.NotFoundError) as exc_info:
        await maybe_await(client.reports.get_report("report-1"))
    assert exc_info.value.body == "not json"


async def test_close_before_any_request_is_a_no_op(client_kind):
    client = make_raw_client(client_kind, _report_handler)
    if client_kind == "sync":
        client.close()
    else:
        await client.aclose()


async def test_concurrent_first_requests_share_one_httpx_client() -> None:
    client = make_raw_client("async", _report_handler)
    results = await asyncio.gather(
        client._get_httpx_client(),
        client._get_httpx_client(),
    )
    assert results[0] is results[1]


async def test_unmapped_non_5xx_status_falls_back_to_bare_api_status_error(client_kind):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/reports/report-1"):
            return httpx2.Response(418, json={})
        return _report_handler(request)

    client = make_raw_client(client_kind, handler)
    with pytest.raises(sp._exceptions.APIStatusError) as exc_info:
        await maybe_await(client.reports.get_report("report-1"))
    assert type(exc_info.value) is sp._exceptions.APIStatusError
    assert exc_info.value.status_code == 418
