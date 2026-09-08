import asyncio

import httpx2
import pytest

import amzn_selling_partner as sp
from amzn_selling_partner import _auth
from tests.conftest import CLIENT_KWARGS, maybe_await

# Captured at collection time, before the autouse `mock_sts_credentials` fixture (in
# conftest.py) replaces `_auth._STSCredentials` with a dummy for every other test.
_RealSTSCredentials = _auth._STSCredentials


def report_json(report_id: str = "report-1") -> dict:
    return {
        "reportId": report_id,
        "reportType": "GET_VENDOR_INVENTORY_REPORT",
        "createdTime": "2023-01-01T00:00:00",
        "processingStatus": "DONE",
    }


def make_raw_client(client_kind: str, handler) -> "sp.Client | sp.AsyncClient":
    transport = httpx2.MockTransport(handler)
    cls = sp.Client if client_kind == "sync" else sp.AsyncClient
    return cls(transport=transport, max_retries=0, **CLIENT_KWARGS)


async def test_signs_requests_with_sigv4_and_lwa_headers(client_factory):
    captured = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        captured.append(request)
        return httpx2.Response(200, json=report_json())

    client = client_factory(handler)
    await maybe_await(client.reports.get_report("report-1"))

    request = captured[0]
    assert request.headers.get("x-amz-access-token") == "test-access-token"
    assert request.headers.get("authorization", "").startswith("AWS4-HMAC-SHA256")
    assert "x-amz-date" in request.headers
    assert request.headers.get("content-type") == "application/json; charset=utf-8"
    assert request.headers.get("accept") == "application/json"
    assert request.headers.get("user-agent", "").startswith("amzn-selling-partner/Python ")


async def test_lwa_token_is_cached_across_requests(client_kind):
    lwa_calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if str(request.url) == _auth.LWA_TOKEN_URL:
            lwa_calls["n"] += 1
            return httpx2.Response(200, json={"access_token": "tok", "expires_in": 3600})
        return httpx2.Response(200, json=report_json())

    client = make_raw_client(client_kind, handler)
    await maybe_await(client.reports.get_report("report-1"))
    await maybe_await(client.reports.get_report("report-1"))

    assert lwa_calls["n"] == 1


async def test_lwa_token_refreshes_after_expiry(client_kind, monkeypatch: pytest.MonkeyPatch):
    lwa_calls = {"n": 0}
    fake_now = {"t": 1_700_000_000.0}
    monkeypatch.setattr(_auth.time, "time", lambda: fake_now["t"])

    def handler(request: httpx2.Request) -> httpx2.Response:
        if str(request.url) == _auth.LWA_TOKEN_URL:
            lwa_calls["n"] += 1
            return httpx2.Response(
                200, json={"access_token": f"tok-{lwa_calls['n']}", "expires_in": 100}
            )
        return httpx2.Response(200, json=report_json())

    client = make_raw_client(client_kind, handler)
    await maybe_await(client.reports.get_report("report-1"))
    assert lwa_calls["n"] == 1

    fake_now["t"] += 200  # advance past the 100s expiry
    await maybe_await(client.reports.get_report("report-1"))
    assert lwa_calls["n"] == 2


async def test_lwa_refresh_failure_raises_spapi_auth_error(client_kind):
    def handler(request: httpx2.Request) -> httpx2.Response:
        if str(request.url) == _auth.LWA_TOKEN_URL:
            return httpx2.Response(400, json={"error": "invalid_grant"})
        raise AssertionError("should not reach the API call when LWA refresh fails")

    client = make_raw_client(client_kind, handler)
    with pytest.raises(sp._exceptions.SPAPIAuthError):
        await maybe_await(client.reports.get_report("report-1"))


def _report_handler(request: httpx2.Request) -> httpx2.Response:
    if str(request.url) == _auth.LWA_TOKEN_URL:
        return httpx2.Response(200, json={"access_token": "tok", "expires_in": 3600})
    return httpx2.Response(200, json=report_json())


async def test_close_releases_pool(client_kind):
    client = make_raw_client(client_kind, _report_handler)
    await maybe_await(client.reports.get_report("report-1"))

    if client_kind == "sync":
        httpx_client = client._httpx_client
        client.close()
    else:
        httpx_client = await client._get_httpx_client()
        await client.aclose()

    assert httpx_client.is_closed


async def test_context_manager_closes_client(client_kind):
    client = make_raw_client(client_kind, _report_handler)

    if client_kind == "sync":
        with client as ctx_client:
            await maybe_await(ctx_client.reports.get_report("report-1"))
        assert client._httpx_client.is_closed
    else:
        async with client as ctx_client:
            await maybe_await(ctx_client.reports.get_report("report-1"))
        assert (await client._get_httpx_client()).is_closed


async def test_async_request_cancellation_is_not_swallowed():
    async def slow_handler(request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(10)
        return httpx2.Response(200, json=report_json())

    client = make_raw_client("async", slow_handler)
    task = asyncio.ensure_future(client.reports.get_report("report-1"))
    await asyncio.sleep(0.05)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


def test_lwa_token_access_token_before_refresh_raises() -> None:
    token = _auth._LWAToken(client_id="a", client_secret="b", refresh_token="c")
    with pytest.raises(RuntimeError):
        _ = token.access_token


class _FakeSTSClient:
    def __init__(self, credentials: dict) -> None:
        self._credentials = credentials
        self.calls: list = []

    def assume_role(self, *, RoleArn: str, RoleSessionName: str) -> dict:
        self.calls.append((RoleArn, RoleSessionName))
        return {"Credentials": self._credentials}


class _FailingSTSClient:
    def assume_role(self, **kwargs: object) -> dict:
        raise RuntimeError("assume_role boom")


def _make_fake_boto3_session(sts_client):
    class FakeSession:
        def __init__(self, **kwargs: object) -> None:
            pass

        def client(self, name: str):
            assert name == "sts"
            return sts_client

    return FakeSession


def test_sts_credentials_builds_refreshable_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    import datetime

    expiration = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    fake_client = _FakeSTSClient(
        {
            "AccessKeyId": "AKIDEXAMPLE",
            "SecretAccessKey": "secret",
            "SessionToken": "token",
            "Expiration": expiration,
        }
    )
    monkeypatch.setattr(_auth.boto3, "Session", _make_fake_boto3_session(fake_client))

    creds = _RealSTSCredentials(
        aws_access_key_id="x",
        aws_secret_access_key="y",
        aws_region="us-east-1",
        aws_role_arn="arn:aws:iam::123456789012:role/example-role",
        aws_role_session_name="session",
    )

    frozen = creds.get_frozen_credentials()
    assert frozen.access_key == "AKIDEXAMPLE"
    assert frozen.secret_key == "secret"
    assert frozen.token == "token"
    assert fake_client.calls == [("arn:aws:iam::123456789012:role/example-role", "session")]


def test_sts_credentials_wraps_assume_role_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_auth.boto3, "Session", _make_fake_boto3_session(_FailingSTSClient()))

    with pytest.raises(sp._exceptions.SPAPIAuthError) as exc_info:
        _RealSTSCredentials(
            aws_access_key_id="x",
            aws_secret_access_key="y",
            aws_region="us-east-1",
            aws_role_arn="arn:aws:iam::123456789012:role/example-role",
            aws_role_session_name="session",
        )

    assert isinstance(exc_info.value.cause, RuntimeError)
