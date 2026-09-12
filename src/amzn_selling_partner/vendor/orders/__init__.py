"""Compatibility ``vendor.orders`` resource over ``amzn_selling_partner``.

Models are the spec-generated ones (``sdk.models.vendor_orders_v1``); the
old enum classes are kept as plain ``str`` enums.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from ... import client as _compat_client
from ..._compat import operation, query_kwargs, require_str, to_body
from .models import (
    AcknowledgementCode,
    InternationalCommercialTerms,
    ItemConfirmationStatus,
    ItemReceiveStatus,
    MethodOfPayment,
    MoneyUnitOfMeasure,
    PaymentMethod,
    PoItemState,
    PurchaseOrderState,
    PurchaseOrderStatus,
    PurchaseOrderType,
    RejectionReason,
    SortOrder,
    TaxRegistrationType,
    UnitOfMeasure,
)


class GetPurchaseOrdersQuery(BaseModel):
    model_config = ConfigDict(extra="allow")

    limit: int | None = None
    createdAfter: str | None = None
    createdBefore: str | None = None
    sortOrder: SortOrder | str | None = None
    nextToken: str | None = None
    includeDetails: str | bool | None = None
    changedAfter: str | None = None
    changedBefore: str | None = None
    poItemState: PoItemState | str | None = None
    isPOChanged: str | bool | None = None
    purchaseOrderState: PurchaseOrderState | str | None = None
    orderingVendorCode: str | None = None


class GetPurchaseOrdersStatusQuery(BaseModel):
    model_config = ConfigDict(extra="allow")

    limit: int | None = None
    sortOrder: SortOrder | str | None = None
    nextToken: str | None = None
    createdAfter: str | None = None
    createdBefore: str | None = None
    updatedAfter: str | None = None
    updatedBefore: str | None = None
    purchaseOrderNumber: str | None = None
    purchaseOrderStatus: PurchaseOrderStatus | str | None = None
    itemConfirmationStatus: ItemConfirmationStatus | str | None = None
    itemReceiveStatus: ItemReceiveStatus | str | None = None
    orderingVendorCode: str | None = None
    shipToPartyId: str | None = None


class Client(_compat_client.BaseClient):
    def get_resource_path(self) -> str:
        return "vendor/orders/v1"

    @property
    def api(self) -> Any:
        return self.sp.vendor_orders_v1

    def _op(self, operation_id: str, *, pages: bool = False) -> Any:
        method = operation(self.sp, "vendor_orders_v1", operation_id)
        return getattr(self.api, f"iter_{method.__name__}") if pages else method

    def get_purchase_orders(self, *, query: GetPurchaseOrdersQuery | dict[str, Any] | None = None) -> list[Any]:
        """All purchase orders matching ``query`` (pages are followed automatically)."""
        return list(self._op("getPurchaseOrders", pages=True)(**query_kwargs(query)))

    def get_purchase_order(self, purchase_order_number: str) -> Any:
        require_str(purchase_order_number, "purchase_order_number")
        return self._op("getPurchaseOrder")(purchase_order_number=purchase_order_number).payload

    def get_purchase_orders_status(self, *, query: GetPurchaseOrdersStatusQuery | dict[str, Any] | None = None) -> list[Any]:
        return list(self._op("getPurchaseOrdersStatus", pages=True)(**query_kwargs(query)))

    def submit_acknowledgement(self, data: Any) -> Any:
        return self._op("submitAcknowledgement")(body=to_body(data))


def __getattr__(name: str) -> Any:
    """Spec-generated models (``Order``, ``OrderDetails``, ``Address``, ...)."""
    from .models import model

    return model(name)


__all__ = [
    "AcknowledgementCode",
    "Client",
    "GetPurchaseOrdersQuery",
    "GetPurchaseOrdersStatusQuery",
    "InternationalCommercialTerms",
    "ItemConfirmationStatus",
    "ItemReceiveStatus",
    "MethodOfPayment",
    "MoneyUnitOfMeasure",
    "PaymentMethod",
    "PoItemState",
    "PurchaseOrderState",
    "PurchaseOrderStatus",
    "PurchaseOrderType",
    "RejectionReason",
    "SortOrder",
    "TaxRegistrationType",
    "UnitOfMeasure",
]
