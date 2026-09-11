"""Enum values kept from the 0.1.x hand-written models plus access to the
spec-generated pydantic models of the Reports API."""

from __future__ import annotations

import enum
from typing import Any

from spapi.plugins.amazon_spapi import default_spec_dir


class ReportType(enum.StrEnum):
    VENDOR_REAL_TIME_INVENTORY_REPORT = "GET_VENDOR_REAL_TIME_INVENTORY_REPORT"
    VENDOR_REAL_TIME_TRAFFIC_REPORT = "GET_VENDOR_REAL_TIME_TRAFFIC_REPORT"
    VENDOR_REAL_TIME_SALES_REPORT = "GET_VENDOR_REAL_TIME_SALES_REPORT"
    VENDOR_SALES_REPORT = "GET_VENDOR_SALES_REPORT"
    VENDOR_NET_PURE_PRODUCT_MARGIN_REPORT = "GET_VENDOR_NET_PURE_PRODUCT_MARGIN_REPORT"
    VENDOR_TRAFFIC_REPORT = "GET_VENDOR_TRAFFIC_REPORT"
    VENDOR_FORECASTING_REPORT = "GET_VENDOR_FORECASTING_REPORT"
    VENDOR_INVENTORY_REPORT = "GET_VENDOR_INVENTORY_REPORT"


class MarketPlaceId(enum.StrEnum):
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


class ProcessingStatus(enum.StrEnum):
    CANCELLED = "CANCELLED"
    DONE = "DONE"
    FATAL = "FATAL"
    IN_PROGRESS = "IN_PROGRESS"
    IN_QUEUE = "IN_QUEUE"


class CompressionAlgorithm(enum.StrEnum):
    GZIP = "GZIP"


class SchedulePeriod(enum.StrEnum):
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


class ReportPeriod(enum.StrEnum):
    DAY = "DAY"
    WEEK = "WEEK"
    MONTH = "MONTH"
    QUARTER = "QUARTER"
    YEAR = "YEAR"


class DistributorView(enum.StrEnum):
    SOURCING = "SOURCING"
    MANUFACTURING = "MANUFACTURING"


class SellingProgram(enum.StrEnum):
    RETAIL = "RETAIL"
    BUSINESS = "BUSINESS"
    FRESH = "FRESH"


_namespace_cache: Any = None


def namespace() -> Any:
    """The spec-generated model namespace for ``reports.v2021_06_30``."""
    global _namespace_cache
    if _namespace_cache is None:
        from spapi.compile.models import build_models
        from spapi.spec.loader import load_document

        path = default_spec_dir() / "reports-api-model" / "reports_2021-06-30.json"
        _namespace_cache = build_models(load_document(path), key="reports.v2021_06_30")
    return _namespace_cache


def model(name: str) -> Any:
    ns = namespace()
    if name not in ns:
        raise AttributeError(f"module 'amzn_selling_partner.reports' has no attribute {name!r}")
    return ns.get(name)


def __getattr__(name: str) -> Any:
    if name.startswith("_"):
        raise AttributeError(name)
    return model(name)
