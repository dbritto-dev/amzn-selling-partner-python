import importlib

import pytest
import requests_aws4auth

import amzn_selling_partner as sp


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
def base_client() -> sp.client.BaseClient:
    return sp.client.BaseClient()


@pytest.fixture
def sandbox_base_client() -> sp.client.BaseClient:
    return sp.client.BaseClient(sandbox=True)


def test_base_client_get_api_endpoint(base_client: sp.client.BaseClient) -> None:
    assert (
        sp.client.SellingPartnerRegion.NORTH_AMERICA.api_endpoint == base_client.get_api_endpoint()
    )


def test_base_client_get_api_sandbox_endpoint(sandbox_base_client: sp.client.BaseClient) -> None:
    assert (
        sp.client.SellingPartnerRegion.NORTH_AMERICA.api_sandbox_endpoint
        == sandbox_base_client.get_api_endpoint()
    )


def test_base_client_get_resource_path(base_client: sp.client.BaseClient) -> None:
    with pytest.raises(NotImplementedError):
        assert "" == base_client.get_resource_path()


def test_base_client_get_resource_endpoint(base_client: sp.client.BaseClient) -> None:
    with pytest.raises(NotImplementedError):
        assert "" == base_client.get_resource_endpoint()


def test_base_client_get_operation_endpoint(base_client: sp.client.BaseClient) -> None:
    with pytest.raises(NotImplementedError):
        assert "" == base_client.get_operation_endpoint("operationMethod")


def test_client_session_auth_reuses_single_access_token_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_module = importlib.import_module("amzn_selling_partner.client.auth")
    importlib.reload(auth_module)

    created_token_instances = []

    class DummyAccessToken:
        def __init__(self, **kwargs):
            created_token_instances.append(kwargs)
            self.data = None

        def get_access_token(self) -> str:
            if self.data is None:
                self.data = {"access_token": "token", "expires_at": 9999999999}
            return self.data["access_token"]

    monkeypatch.setattr(
        auth_module,
        "ClientSessionAuthTemporaryCredentials",
        type(
            "DummyTemporaryCredentials",
            (),
            {"__init__": lambda _, *args, **kwargs: None, "get_refreshable_credentials": lambda _: object()},
        ),
    )
    monkeypatch.setattr(requests_aws4auth.AWS4Auth, "__init__", lambda self, *args, **kwargs: None)
    monkeypatch.setattr(auth_module, "ClientSessionAuthAccessToken", DummyAccessToken)

    auth = auth_module.ClientSessionAuth(
        selling_partner_app_client_id="client-id",
        selling_partner_app_client_secret="client-secret",
        selling_partner_app_refresh_token="refresh-token",
        aws_access_key_id="aws-access-key-id",
        aws_secret_access_key="aws-secret-access-key",
        aws_region="us-east-1",
        aws_selling_partner_role="role-arn",
        aws_selling_partner_role_session_name="session-name",
    )

    assert auth._get_access_token() == "token"
    assert auth._get_access_token() == "token"
    assert len(created_token_instances) == 1
