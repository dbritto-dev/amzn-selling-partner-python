"""Enum values kept from the 0.1.x hand-written models plus access to the
spec-generated pydantic models of the Reports API."""

from __future__ import annotations

import enum
from typing import Any


class ReportType(str, enum.Enum):
    VENDOR_REAL_TIME_INVENTORY_REPORT = "GET_VENDOR_REAL_TIME_INVENTORY_REPORT"
    VENDOR_REAL_TIME_TRAFFIC_REPORT = "GET_VENDOR_REAL_TIME_TRAFFIC_REPORT"
    VENDOR_REAL_TIME_SALES_REPORT = "GET_VENDOR_REAL_TIME_SALES_REPORT"
    VENDOR_SALES_REPORT = "GET_VENDOR_SALES_REPORT"
    VENDOR_NET_PURE_PRODUCT_MARGIN_REPORT = "GET_VENDOR_NET_PURE_PRODUCT_MARGIN_REPORT"
    VENDOR_TRAFFIC_REPORT = "GET_VENDOR_TRAFFIC_REPORT"
    VENDOR_FORECASTING_REPORT = "GET_VENDOR_FORECASTING_REPORT"
    VENDOR_INVENTORY_REPORT = "GET_VENDOR_INVENTORY_REPORT"


class MarketPlaceId(str, enum.Enum):
    CANADA = "A2EUQ1WTGCTBG2"
    UNITED_STATES_OF_AMERICA = "ATVPDKIKX0DER"
    MEXICO = "A1AM78C64UM0Y8"
    BRAZIL = "A2Q3Y263D00KWC"
    SPAIN = "A1RKKUPIHCS9HS"
    UNITED_KINGDOM = "A1F83G8C2ARO7P"
    FRANCE = "A13V1IB3VIYZZH"
    BELGIUM = "AMEN7PMS3EDWL"
    NETHERLANDS = "A1805IZSGTT6HS"
    GERMANY = "A1PA6795UKMFR9"
    ITALY = "APJ6JRA9NG5V4"
    SWEDEN = "A2NODRKZP88ZB9"
    POLAND = "A1C3SOZRARQ6R3"
    EGYPT = "ARBP9OOSHTCHU"
    TURKEY = "A33AVAJ2PDY3EV"
    SAUDI_ARABIA = "A17E79C6D8DWNP"
    UNITED_ARAB_EMIRATES = "A2VIGQ35RCS4UG"
    INDIA = "A21TJRUUN4KGV"
    SINGAPORE = "A19VAU5U5O7RUS"
    AUSTRALIA = "A39IBJ37TRP1C6"
    JAPAN = "A1VC38T7YXB528"


class ProcessingStatus(str, enum.Enum):
    CANCELLED = "CANCELLED"
    DONE = "DONE"
    FATAL = "FATAL"
    IN_PROGRESS = "IN_PROGRESS"
    IN_QUEUE = "IN_QUEUE"


class CompressionAlgorithm(str, enum.Enum):
    GZIP = "GZIP"


class SchedulePeriod(str, enum.Enum):
    FIVE_MINUTES = "PT5M"
    FIFTEEN_MINUTES = "PT15M"
    THIRTY_MINUTES = "PT30M"
    ONE_HOUR = "PT1H"
    TWO_HOURS = "PT2H"
    FOUR_HOURS = "PT4H"
    EIGHT_HOURS = "PT8H"
    TWELVE_HOURS = "PT12H"
    ONE_DAY = "P1D"
    TWO_DAYS = "P2D"
    THREE_DAYS = "P3D"
    EIGHTY_FOUR_HOURS = "PT84H"
    ONE_WEEK = "P7D"
    TWO_WEEKS = "P14D"
    FIFTEEN_DAYS = "P15D"
    EIGHTEEN_DAYS = "P18D"
    THIRTY_DAYS = "P30D"
    ONE_MONTH = "P1M"


class ReportPeriod(str, enum.Enum):
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    QUARTER = "QUARTER"
    YEAR = "YEAR"


class DistributorView(str, enum.Enum):
    SOURCING = "SOURCING"
    MANUFACTURING = "MANUFACTURING"


class SellingProgram(str, enum.Enum):
    RETAIL = "RETAIL"
    BUSINESS = "BUSINESS"
    FRESH = "FRESH"


def namespace() -> Any:
    """The generated models module for ``reports``."""
    import importlib

    return importlib.import_module("amzn_selling_partner.sdk.models.reports_v2021_06_30")


def model(name: str) -> Any:
    ns = namespace()
    if name not in ns.__all__:
        raise AttributeError(f"module 'amzn_selling_partner.reports' has no attribute {name!r}")
    return getattr(ns, name)


def __getattr__(name: str) -> Any:
    if name.startswith("_"):
        raise AttributeError(name)
    return model(name)
