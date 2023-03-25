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
def reports_client() -> sp.reports.Client:
    return sp.reports.Client()


def test_reports_client_get_resource_path(reports_client: sp.reports.Client) -> None:
    assert "reports/2021-06-30" == reports_client.get_resource_path()


def test_reports_client_get_resource_endpoint(reports_client: sp.reports.Client) -> None:
    assert (
        f"{sp.client.SellingPartnerRegion.NORTH_AMERICA.api_endpoint}/reports/2021-06-30"
        == reports_client.get_resource_endpoint()
    )


def test_reports_client_get(reports_client: sp.reports.Client) -> None:
    assert (
        f"{sp.client.SellingPartnerRegion.NORTH_AMERICA.api_endpoint}/reports/2021-06-30/operationMethod"
        == reports_client.get_operation_endpoint("operationMethod")
    )
