"""Enum values kept from the 0.1.x hand-written models plus access to the
spec-generated pydantic models of the Vendor Orders API."""

from __future__ import annotations

import enum
from typing import Any


class PurchaseOrderType(str, enum.Enum):
    REGULAR_ORDER = "RegularOrder"
    CONSIGNED_ORDER = "ConsignedOrder"
    NEW_PRODUCT_INTRODUCTION = "NewProductIntroduction"
    RUSH_ORDER = "RushOrder"


class PurchaseOrderState(str, enum.Enum):
    NEW = "New"
    ACKNOWLEDGED = "Acknowledged"
    CLOSED = "Closed"


class UnitOfMeasure(str, enum.Enum):
    CASES = "Cases"
    EACHES = "Eaches"


class MoneyUnitOfMeasure(str, enum.Enum):
    POUNDS = "POUNDS"
    OUNCES = "OUNCES"
    GRAMS = "GRAMS"
    KILOGRAMS = "KILOGRAMS"


class MethodOfPayment(str, enum.Enum):
    PAID_BY_BUYER = "PaidByBuyer"
    COLLECT_ON_DELIVERY = "CollectOnDelivery"
    DEFINED_BY_BUYER_AND_SELLER = "DefinedByBuyerAndSeller"
    FOB_PORT_OF_CALL = "FOBPortOfCall"
    PREPAID_BY_SELLER = "PrepaidBySeller"
    PAID_BY_SELLER = "PaidBySeller"


class InternationalCommercialTerms(str, enum.Enum):
    EX_WORKS = "ExWorks"
    FREE_CARRIER = "FreeCarrier"
    FREE_ON_BOARD = "FreeOnBoard"
    FREE_ALONG_SIDE_SHIP = "FreeAlongSideShip"
    CARRIAGE_PAID_TO = "CarriagePaidTo"
    COST_AND_FREIGHT = "CostAndFreight"
    CARRIAGE_AND_INSURANCE_PAID_TO = "CarriageAndInsurancePaidTo"
    COST_INSURANCE_AND_FREIGHT = "CostInsuranceAndFreight"
    DELIVERED_AT_TERMINAL = "DeliveredAtTerminal"
    DELIVERED_AT_PLACE = "DeliveredAtPlace"
    DELIVER_DUTY_PAID = "DeliverDutyPaid"


class TaxRegistrationType(str, enum.Enum):
    VALUE_ADDED_TAX = "VAT"
    GOODS_AND_SERVICES_TAX = "GST"


class PaymentMethod(str, enum.Enum):
    INVOICE = "Invoice"
    CONSIGNMENT = "Consignment"
    CREDIT_CARD = "CreditCard"
    PREPAID = "Prepaid"


class SortOrder(str, enum.Enum):
    ASCENDING = "ASC"
    DESCENDING = "DESC"


class PoItemState(str, enum.Enum):
    CANCELLED = "Cancelled"


class AcknowledgementCode(str, enum.Enum):
    ACCEPTED = "Accepted"
    BACKORDERED = "Backordered"
    REJECTED = "Rejected"


class RejectionReason(str, enum.Enum):
    TEMPORARILY_UNAVAILABLE = "TemporarilyUnavailable"
    INVALID_PRODUCT_IDENTIFIER = "InvalidProductIdentifier"
    OBSOLETE_PRODUCT = "ObsoleteProduct"


class PurchaseOrderStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ItemConfirmationStatus(str, enum.Enum):
    ACCEPTED = "ACCEPTED"
    PARTIALLY_ACCEPTED = "PARTIALLY_ACCEPTED"
    REJECTED = "REJECTED"
    UNCONFIRMED = "UNCONFIRMED"


class ItemReceiveStatus(str, enum.Enum):
    NOT_RECEIVED = "NOT_RECEIVED"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED = "RECEIVED"


def namespace() -> Any:
    """The generated models module for ``vendor_orders``."""
    import importlib

    return importlib.import_module("amzn_selling_partner.sdk.models.vendor_orders_v1")


def model(name: str) -> Any:
    ns = namespace()
    if name not in ns.__all__:
        raise AttributeError(f"module 'amzn_selling_partner.vendor.orders' has no attribute {name!r}")
    return getattr(ns, name)


def __getattr__(name: str) -> Any:
    if name.startswith("_"):
        raise AttributeError(name)
    return model(name)
