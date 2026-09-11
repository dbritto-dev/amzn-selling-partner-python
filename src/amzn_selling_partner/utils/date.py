import datetime
import typing


def datetime_utcnow() -> datetime.datetime:
    """Naive UTC "now" (same contract as before, without ``utcnow()``)."""
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def datetime_utcpast(
    amount: int | float,
    amount_type: typing.Literal["weeks", "days", "hours", "minutes", "seconds", "milliseconds", "microseconds"],
) -> datetime.datetime:
    return datetime_utcnow() - datetime.timedelta(**{amount_type: amount})


def amazon_isoformat(value: datetime.datetime) -> str:
    return f"{value.isoformat(timespec='milliseconds')}Z"
