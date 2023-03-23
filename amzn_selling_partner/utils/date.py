import datetime
import typing


def datetime_utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()


def date_utcnow() -> datetime.date:
    return datetime_utcnow().date()


def datetime_utcpast(
    amount: typing.Union[int, float],
    amount_type: typing.Literal[
        "weeks", "days", "hours", "minutes", "seconds", "milliseconds", "microseconds"
    ],
) -> datetime.datetime:
    return datetime_utcnow() - datetime.timedelta(**{amount_type: amount})


def date_utcpast(
    amount: typing.Union[int, float],
    amount_type: typing.Literal[
        "weeks", "days", "hours", "minutes", "seconds", "milliseconds", "microseconds"
    ],
) -> datetime.date:
    return datetime_utcpast(amount, amount_type).date()


def amazon_isoformat(value: typing.Union[datetime.date, datetime.datetime]) -> str:
    return f"{value.isoformat(timespec='milliseconds')}Z"
