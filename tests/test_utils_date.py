import datetime

import pytest

import amzn_selling_partner as sp


@pytest.fixture(autouse=True)
def mock_datetime_utcnow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        datetime,
        "datetime",
        type(
            "mockdatetime",
            (datetime.datetime,),
            {"utcnow": classmethod(lambda _: datetime.datetime(2023, 1, 1))},
        ),
    )


def test_datetime_utcnow() -> None:
    assert "2023-01-01T00:00:00" == sp.utils.date.datetime_utcnow().isoformat()


def test_datetime_utcpast() -> None:
    assert "2022-12-02T00:00:00" == sp.utils.date.datetime_utcpast(30, "days").isoformat()


def test_amazon_isoformat() -> None:
    assert "2023-01-01T00:00:00.000Z" == sp.utils.date.amazon_isoformat(
        sp.utils.date.datetime_utcnow()
    )
