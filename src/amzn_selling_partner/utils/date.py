import datetime
import typing


def datetime_utcnow() -> datetime.datetime:
    return datetime.datetime.utcnow()


def datetime_utcpast(
    amount: typing.Union[int, float],
    amount_type: typing.Literal[
        "weeks", "days", "hours", "minutes", "seconds", "milliseconds", "microseconds"
    ],
) -> datetime.datetime:
    return datetime_utcnow() - datetime.timedelta(**{amount_type: amount})


def amazon_isoformat(value: datetime.datetime) -> str:
    return f"{value.isoformat(timespec='milliseconds')}Z"
