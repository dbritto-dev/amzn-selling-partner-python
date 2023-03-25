import pytest

import amzn_selling_partner as sp


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
