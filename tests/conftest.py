import inspect
import typing

import botocore.credentials
import httpx2
import pytest

import amzn_selling_partner as sp

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"  # noqa

Handler = typing.Callable[[httpx2.Request], httpx2.Response]


async def maybe_await(value: typing.Any) -> typing.Any:
    if inspect.isawaitable(value):
        return await value
    return value


class DummySTSCredentials:
    """Replaces `_auth._STSCredentials` in every test so constructing a `Client`/
    `AsyncClient` never makes a real AWS STS `assume_role` call, mirroring the old
    `mock_client_session_auth` fixture that replaced `ClientSessionAuth` wholesale."""

    aws_region = "us-east-1"

    def __init__(self, **kwargs: object) -> None:
        pass

    def get_frozen_credentials(self) -> botocore.credentials.ReadOnlyCredentials:
        return botocore.credentials.ReadOnlyCredentials("AKIDEXAMPLE", "secret-key", "token")


@pytest.fixture(autouse=True)
def mock_sts_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sp._auth, "_STSCredentials", DummySTSCredentials)


def lwa_token_response(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, json={"access_token": "test-access-token", "expires_in": 3600})


def with_lwa(api_handler: Handler) -> Handler:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if str(request.url) == LWA_TOKEN_URL:
            return lwa_token_response(request)
        return api_handler(request)

    return handler


CLIENT_KWARGS: typing.Dict[str, object] = {
    "selling_partner_app_client_id": "client-id",
    "selling_partner_app_client_secret": "client-secret",
    "selling_partner_app_refresh_token": "refresh-token",
    "aws_access_key_id": "AKIDEXAMPLE",
    "aws_secret_access_key": "secret-key",
    "aws_selling_partner_role": "arn:aws:iam::123456789012:role/example-role",
    "aws_selling_partner_role_session_name": "session",
}


def make_client(
    kind: str, api_handler: Handler, **kwargs: object
) -> typing.Union["sp.Client", "sp.AsyncClient"]:
    transport = httpx2.MockTransport(with_lwa(api_handler))
    cls = sp.Client if kind == "sync" else sp.AsyncClient
    merged_kwargs: typing.Dict[str, object] = {"max_retries": 0, **CLIENT_KWARGS, **kwargs}
    return cls(transport=transport, **merged_kwargs)


@pytest.fixture(params=["sync", "async"], ids=["sync", "async"])
def client_kind(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
def client_factory(
    client_kind: str,
) -> typing.Callable[..., typing.Union["sp.Client", "sp.AsyncClient"]]:
    def _factory(
        api_handler: Handler, **kwargs: object
    ) -> typing.Union["sp.Client", "sp.AsyncClient"]:
        return make_client(client_kind, api_handler, **kwargs)

    return _factory
