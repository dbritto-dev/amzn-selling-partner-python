import datetime

import pytest

import amzn_selling_partner.utils.date as sp_date_utils


@pytest.fixture(autouse=True)
def mock_datetime_utcnow(monkeypatch: pytest.MonkeyPatch) -> datetime.datetime:
    mock_datetime = type(
        "mockdatetime",
        (datetime.datetime,),
        {"utcnow": classmethod(lambda _: datetime.datetime(2023, 1, 1))},
    )
    monkeypatch.setattr(datetime, "datetime", mock_datetime)


def test_datetime_utcnow() -> None:
    assert "2023-01-01T00:00:00" == sp_date_utils.datetime_utcnow().isoformat()


def test_datetime_utcpast() -> None:
    assert "2022-12-02T00:00:00" == sp_date_utils.datetime_utcpast(30, "days").isoformat()


def test_amazon_isoformat() -> None:
    assert "2023-01-01T00:00:00.000Z" == sp_date_utils.amazon_isoformat(
        sp_date_utils.datetime_utcnow()
    )
