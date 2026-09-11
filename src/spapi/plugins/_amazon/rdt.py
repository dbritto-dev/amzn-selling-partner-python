"""Restricted Data Token (RDT) requirements and grantless scopes.

Hand-maintained; the specs do not mark restricted operations. Source:
https://developer-docs.amazon.com/sp-api/docs/tokens-api-use-case-guide
(restricted operations table) and the grantless-operations page. Last
reviewed against the pinned models: 2026-09-10.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True, kw_only=True)
class RestrictedOperation:
    #: ``None`` -> always needs an RDT. Otherwise the operation returns PII only
    #: when the caller opts in (``RequestOptions(auth={"rdt": True})`` /
    #: ``with_rdt(...)``); the tuple lists the dataElements such a request may
    #: ask for (empty for report documents, whose PII depends on the report type).
    data_elements: tuple[str, ...] | None = None


_ALWAYS = RestrictedOperation()
_ORDER_PII = RestrictedOperation(data_elements=("buyerInfo", "shippingAddress", "buyerTaxInformation"))

# (api, version or None, operationId) -> requirement
RESTRICTED: dict[tuple[str, str | None, str], RestrictedOperation] = {
    ("orders", "v0", "getOrders"): _ORDER_PII,
    ("orders", "v0", "getOrder"): _ORDER_PII,
    ("orders", "v0", "getOrderItems"): _ORDER_PII,
    ("orders", "v0", "getOrderBuyerInfo"): _ALWAYS,
    ("orders", "v0", "getOrderAddress"): _ALWAYS,
    ("orders", "v0", "getOrderItemsBuyerInfo"): _ALWAYS,
    ("orders", "v0", "getOrderRegulatedInfo"): _ALWAYS,
    ("orders", "v2026_01_01", "searchOrders"): _ORDER_PII,
    ("orders", "v2026_01_01", "getOrder"): _ORDER_PII,
    ("merchant_fulfillment", "v0", "createShipment"): _ALWAYS,
    ("merchant_fulfillment", "v0", "getShipment"): _ALWAYS,
    ("merchant_fulfillment", "v0", "cancelShipment"): _ALWAYS,
    ("shipping", "v1", "createShipment"): _ALWAYS,
    ("shipping", "v1", "getShipment"): _ALWAYS,
    ("shipping", "v1", "cancelShipment"): _ALWAYS,
    ("shipping", "v1", "purchaseLabels"): _ALWAYS,
    ("shipping", "v1", "retrieveShippingLabel"): _ALWAYS,
    ("shipping", "v1", "purchaseShipment"): _ALWAYS,
    ("easy_ship", None, "createScheduledPackage"): _ALWAYS,
    ("easy_ship", None, "getScheduledPackage"): _ALWAYS,
    ("easy_ship", None, "updateScheduledPackages"): _ALWAYS,
    ("easy_ship", None, "createScheduledPackageBulk"): _ALWAYS,
    ("vendor_direct_fulfillment_orders", None, "getOrders"): _ALWAYS,
    ("vendor_direct_fulfillment_orders", None, "getOrder"): _ALWAYS,
    ("vendor_direct_fulfillment_shipping", None, "getShippingLabels"): _ALWAYS,
    ("vendor_direct_fulfillment_shipping", None, "getShippingLabel"): _ALWAYS,
    ("vendor_direct_fulfillment_shipping", None, "getCustomerInvoices"): _ALWAYS,
    ("vendor_direct_fulfillment_shipping", None, "getCustomerInvoice"): _ALWAYS,
    ("vendor_direct_fulfillment_shipping", None, "getPackingSlips"): _ALWAYS,
    ("vendor_direct_fulfillment_shipping", None, "getPackingSlip"): _ALWAYS,
    ("reports", None, "getReportDocument"): RestrictedOperation(data_elements=()),  # only for restricted report types
}

#: Report types whose documents contain PII and need an RDT for getReportDocument.
RESTRICTED_REPORT_TYPES: frozenset[str] = frozenset(
    {
        "GET_AMAZON_FULFILLED_SHIPMENTS_DATA_GENERAL",
        "GET_AMAZON_FULFILLED_SHIPMENTS_DATA_INVOICING",
        "GET_AMAZON_FULFILLED_SHIPMENTS_DATA_TAX",
        "GET_FLAT_FILE_ACTIONABLE_ORDER_DATA_SHIPPING",
        "GET_FLAT_FILE_ORDER_REPORT_DATA_SHIPPING",
        "GET_FLAT_FILE_ORDER_REPORT_DATA_INVOICING",
        "GET_FLAT_FILE_ORDER_REPORT_DATA_TAX",
        "GET_FLAT_FILE_ORDERS_RECONCILIATION_DATA_TAX",
        "GET_FLAT_FILE_ORDERS_RECONCILIATION_DATA_INVOICING",
        "GET_FLAT_FILE_ORDERS_RECONCILIATION_DATA_SHIPPING",
        "GET_ORDER_REPORT_DATA_INVOICING",
        "GET_ORDER_REPORT_DATA_TAX",
        "GET_ORDER_REPORT_DATA_SHIPPING",
        "GET_EASYSHIP_DOCUMENTS",
        "GET_GST_MTR_B2B_CUSTOM",
        "GET_VAT_TRANSACTION_DATA",
        "SC_VAT_TAX_REPORT",
        "GET_FLAT_FILE_ALL_ORDERS_DATA_BY_LAST_UPDATE_GENERAL",
        "GET_FLAT_FILE_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL",
        "GET_XML_ALL_ORDERS_DATA_BY_LAST_UPDATE_GENERAL",
        "GET_XML_ALL_ORDERS_DATA_BY_ORDER_DATE_GENERAL",
        "GET_FLAT_FILE_PENDING_ORDERS_DATA",
        "GET_PENDING_ORDERS_DATA",
        "GET_CONVERGED_FLAT_FILE_PENDING_ORDERS_DATA",
        "GET_FLAT_FILE_RETURNS_DATA_BY_RETURN_DATE",
        "GET_XML_RETURNS_DATA_BY_RETURN_DATE",
        "GET_XML_MFN_PRIME_RETURNS_REPORT",
        "GET_CSV_MFN_PRIME_RETURNS_REPORT",
        "GET_XML_MFN_SKU_RETURN_ATTRIBUTES_REPORT",
        "GET_FLAT_FILE_MFN_SKU_RETURN_ATTRIBUTES_REPORT",
    }
)

#: Grantless operations -> required LWA scopes.
GRANTLESS: dict[tuple[str, str], tuple[str, ...]] = {
    ("notifications", "getSubscriptionById"): ("sellingpartnerapi::notifications",),
    ("notifications", "deleteSubscriptionById"): ("sellingpartnerapi::notifications",),
    ("notifications", "sendTestNotification"): ("sellingpartnerapi::notifications",),
    ("notifications", "getDestinations"): ("sellingpartnerapi::notifications",),
    ("notifications", "createDestination"): ("sellingpartnerapi::notifications",),
    ("notifications", "getDestination"): ("sellingpartnerapi::notifications",),
    ("notifications", "deleteDestination"): ("sellingpartnerapi::notifications",),
    ("application", "rotateApplicationClientSecret"): ("sellingpartnerapi::client_credential:rotation",),
}


def restricted_for(api: str, version: str, operation_id: str) -> RestrictedOperation | None:
    r = RESTRICTED.get((api, version, operation_id))
    if r is None:
        r = RESTRICTED.get((api, None, operation_id))
    return r


__all__ = ["GRANTLESS", "RESTRICTED", "RESTRICTED_REPORT_TYPES", "RestrictedOperation", "restricted_for"]
