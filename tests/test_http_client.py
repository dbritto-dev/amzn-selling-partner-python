import httpx2

import amzn_selling_partner as sp
from tests.conftest import CLIENT_KWARGS, maybe_await
from tests.test_auth import _report_handler


def make_client_with_http_client(client_kind: str, http_client) -> "sp.Client | sp.AsyncClient":
    cls = sp.Client if client_kind == "sync" else sp.AsyncClient
    return cls(http_client=http_client, max_retries=0, **CLIENT_KWARGS)


async def test_user_supplied_http_client_still_gets_base_url_and_auth(client_kind):
    # A bare httpx2 client with no base_url and no auth configured -- exactly what a
    # caller would hand in via `http_client=`. Regression test for a real bug: auth/URL
    # resolution used to be delegated to the underlying httpx2 client's own config, which
    # is empty for a caller-supplied client.
    if client_kind == "sync":
        bare_client = httpx2.Client(transport=httpx2.MockTransport(_report_handler))
    else:
        bare_client = httpx2.AsyncClient(transport=httpx2.MockTransport(_report_handler))

    client = make_client_with_http_client(client_kind, bare_client)
    report = await maybe_await(client.reports.get_report("report-1"))
    assert report.reportId == "report-1"


async def test_default_httpx_client_helpers_are_importable_and_constructible() -> None:
    sync_client = sp.DefaultHttpxClient()
    async_client = sp.DefaultAsyncHttpxClient()
    try:
        assert sync_client.timeout is not None
        assert async_client.timeout is not None
    finally:
        sync_client.close()
        await async_client.aclose()


async def test_default_aiohttp_client_works_as_http_client_override() -> None:
    # DefaultAioHttpClient is an httpx2.AsyncClient subclass, so a transport override for
    # testing works the same way it does for any other httpx2 client.
    http_client = sp.DefaultAioHttpClient(transport=httpx2.MockTransport(_report_handler))
    client = make_client_with_http_client("async", http_client)
    try:
        report = await client.reports.get_report("report-1")
        assert report.reportId == "report-1"
    finally:
        await client.aclose()


async def test_default_aiohttp_client_is_never_used_automatically() -> None:
    # No aiohttp auto-detection: constructing a plain AsyncClient never picks the aiohttp
    # transport on its own, even though the `aiohttp` extra is installed in this dev
    # environment. Opting in requires `http_client=DefaultAioHttpClient()` explicitly.
    client = sp.AsyncClient(**CLIENT_KWARGS)
    try:
        httpx_client = await client._get_httpx_client()
        assert isinstance(httpx_client, sp.DefaultAsyncHttpxClient)
        assert not isinstance(httpx_client, sp.DefaultAioHttpClient)
    finally:
        await client.aclose()
