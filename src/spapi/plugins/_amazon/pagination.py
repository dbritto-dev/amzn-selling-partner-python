"""Pagination overrides for operations the generic heuristic cannot settle,
plus the operations whose other parameters must be omitted when a token is
supplied."""

from __future__ import annotations

from ...runtime._pagination import Pagination

# (api, version, operationId) -> descriptor. ``None`` version matches all.
OVERRIDES: dict[tuple[str, str | None, str], Pagination] = {
    ("orders", "v0", "getOrders"): Pagination(items_path="payload.Orders", next_token_path="payload.NextToken", next_token_param="NextToken", drop_params_on_next=True),
    ("orders", "v0", "getOrderItems"): Pagination(items_path="payload.OrderItems", next_token_path="payload.NextToken", next_token_param="NextToken", drop_params_on_next=True),
    ("orders", "v0", "getOrderItemsBuyerInfo"): Pagination(items_path="payload.OrderItems", next_token_path="payload.NextToken", next_token_param="NextToken", drop_params_on_next=True),
    ("reports", None, "getReports"): Pagination(items_path="reports", next_token_path="nextToken", next_token_param="nextToken", drop_params_on_next=True),
    ("feeds", None, "getFeeds"): Pagination(items_path="feeds", next_token_path="nextToken", next_token_param="nextToken", drop_params_on_next=True),
    ("catalog_items", "v2020_12_01", "searchCatalogItems"): Pagination(items_path="items", next_token_path="pagination.nextToken", next_token_param="pageToken", prev_token_path="pagination.previousToken", drop_params_on_next=False),
    ("catalog_items", "v2022_04_01", "searchCatalogItems"): Pagination(items_path="items", next_token_path="pagination.nextToken", next_token_param="pageToken", prev_token_path="pagination.previousToken", drop_params_on_next=False),
    ("listings_items", "v2021_08_01", "searchListingsItems"): Pagination(items_path="items", next_token_path="pagination.nextToken", next_token_param="pageToken", prev_token_path="pagination.previousToken"),
    ("data_kiosk", None, "getQueries"): Pagination(items_path="queries", next_token_path="pagination.nextToken", next_token_param="paginationToken", drop_params_on_next=True),
    ("fba_inventory", None, "getInventorySummaries"): Pagination(items_path="payload.inventorySummaries", next_token_path="pagination.nextToken", next_token_param="nextToken", drop_params_on_next=True),
    ("notifications", None, "getSubscriptions"): Pagination(items_path="payload.subscriptions", next_token_path="payload.nextToken", next_token_param="nextToken", drop_params_on_next=True),
    ("aplus_content", None, "searchContentDocuments"): Pagination(items_path="contentMetadataRecords", next_token_path="nextPageToken", next_token_param="pageToken"),
    ("aplus_content", None, "listContentDocumentAsinRelations"): Pagination(items_path="asinMetadataSet", next_token_path="nextPageToken", next_token_param="pageToken"),
    ("aplus_content", None, "searchContentPublishRecords"): Pagination(items_path="publishRecordList", next_token_path="nextPageToken", next_token_param="pageToken"),
    ("services", None, "getServiceJobs"): Pagination(items_path="payload.jobs", next_token_path="payload.nextPageToken", next_token_param="pageToken", prev_token_path="payload.previousPageToken"),
    ("fulfillment_inbound", "v2024_03_20", "getSelfShipAppointmentSlots"): Pagination(items_path="selfShipAppointmentSlotsAvailability.slots", next_token_path="pagination.nextToken", next_token_param="paginationToken"),
    ("promotions", None, "getSelection"): Pagination(items_path="selection.selectionDetails.items", next_token_path="selection.selectionDetails.pagination.nextToken", next_token_param="paginationToken"),
    ("finances", "v0", "listFinancialEventGroups"): Pagination(items_path="payload.FinancialEventGroupList", next_token_path="payload.NextToken", next_token_param="NextToken", drop_params_on_next=True),
    ("finances", "v0", "listFinancialEventsByGroupId"): Pagination(items_path="payload.FinancialEvents", next_token_path="payload.NextToken", next_token_param="NextToken", items_is_object=True, drop_params_on_next=True),
    ("finances", "v0", "listFinancialEventsByOrderId"): Pagination(items_path="payload.FinancialEvents", next_token_path="payload.NextToken", next_token_param="NextToken", items_is_object=True, drop_params_on_next=True),
    ("finances", "v0", "listFinancialEvents"): Pagination(items_path="payload.FinancialEvents", next_token_path="payload.NextToken", next_token_param="NextToken", items_is_object=True, drop_params_on_next=True),
}

#: Operations whose ``nextToken`` description says the other parameters must be
#: omitted (checked against the pinned specs by a test).
DROP_PARAMS_ON_NEXT: frozenset[tuple[str, str]] = frozenset(
    {
        ("orders", "getOrders"),
        ("orders", "getOrderItems"),
        ("orders", "getOrderItemsBuyerInfo"),
        ("reports", "getReports"),
        ("feeds", "getFeeds"),
        ("data_kiosk", "getQueries"),
        ("fba_inventory", "getInventorySummaries"),
        ("notifications", "getSubscriptions"),
        ("finances", "listFinancialEventGroups"),
        ("finances", "listFinancialEventsByGroupId"),
        ("finances", "listFinancialEventsByOrderId"),
        ("finances", "listFinancialEvents"),
    }
)


def override_for(api: str, version: str, operation_id: str) -> Pagination | None:
    p = OVERRIDES.get((api, version, operation_id))
    if p is None:
        p = OVERRIDES.get((api, None, operation_id))
    return p


__all__ = ["DROP_PARAMS_ON_NEXT", "OVERRIDES", "override_for"]
