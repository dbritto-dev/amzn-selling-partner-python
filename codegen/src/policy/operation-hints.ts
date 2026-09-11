import type { OperationHint } from '@workos/oagen';

/**
 * Per-operation overrides for the operation resolver. Keyed by `"METHOD /path"`.
 *
 * Method names come from oagen's resolver; only the operations whose derived
 * names collide within their API version are listed (`npm run sdk:resolve --
 * --format table` shows the full table, the generator reports collisions as
 * notes and suffixes the second one). The algorithm handles the rest.
 */
export const operationHints: Record<string, OperationHint> = {
  // -- A+ Content 2020-11-01 ---------------------------------------------------
  'POST /aplus/2020-11-01/contentDocuments': { name: 'create_content_document' },
  'POST /aplus/2020-11-01/contentDocuments/{contentReferenceKey}': { name: 'update_content_document' },

  // -- Customer Feedback 2024-06-01 --------------------------------------------
  'GET /customerFeedback/2024-06-01/items/{asin}/reviews/topics': { name: 'get_item_review_topics' },
  'GET /customerFeedback/2024-06-01/browseNodes/{browseNodeId}/reviews/topics': { name: 'get_browse_node_review_topics' },
  'GET /customerFeedback/2024-06-01/items/{asin}/reviews/trends': { name: 'get_item_review_trends' },
  'GET /customerFeedback/2024-06-01/browseNodes/{browseNodeId}/reviews/trends': { name: 'get_browse_node_review_trends' },
  'GET /customerFeedback/2024-06-01/browseNodes/{browseNodeId}/returns/topics': { name: 'get_browse_node_return_topics' },
  'GET /customerFeedback/2024-06-01/browseNodes/{browseNodeId}/returns/trends': { name: 'get_browse_node_return_trends' },

  // -- External Fulfillment 2024-09-11 -----------------------------------------
  'PUT /externalFulfillment/2024-09-11/shipments/{shipmentId}/packages/{packageId}': { name: 'update_package' },
  'PATCH /externalFulfillment/2024-09-11/shipments/{shipmentId}/packages/{packageId}': { name: 'update_package_status' },

  // -- Fulfillment Inbound v0 --------------------------------------------------
  'GET /fba/inbound/v0/shipments/{shipmentId}/items': { name: 'get_shipment_items_by_shipment_id' },
  'GET /fba/inbound/v0/shipmentItems': { name: 'get_shipment_items' },

  // -- Fulfillment Outbound 2020-07-01 -----------------------------------------
  'GET /fba/outbound/2020-07-01/features/inventory/{featureName}': { name: 'get_feature_inventory' },
  'GET /fba/outbound/2020-07-01/features/inventory/{featureName}/{sellerSku}': { name: 'get_feature_sku' },

  // -- Listings Items 2020-09-01 / 2021-08-01 ----------------------------------
  // PUT and PATCH on the same path both derive `update_item`; keep the verbs apart.
  'PUT /listings/2020-09-01/items/{sellerId}/{sku}': { name: 'put_listings_item' },
  'PATCH /listings/2020-09-01/items/{sellerId}/{sku}': { name: 'patch_listings_item' },
  'PUT /listings/2021-08-01/items/{sellerId}/{sku}': { name: 'put_listings_item' },
  'PATCH /listings/2021-08-01/items/{sellerId}/{sku}': { name: 'patch_listings_item' },
  'GET /listings/2021-08-01/items/{sellerId}/{sku}': { name: 'get_listings_item' },
  'GET /listings/2021-08-01/items/{sellerId}': { name: 'search_listings_items' },

  // -- Notifications v1 --------------------------------------------------------
  'GET /notifications/v1/subscriptions/{notificationType}': { name: 'get_subscription' },
  'GET /notifications/v1/subscriptions/{notificationType}/{subscriptionId}': { name: 'get_subscription_by_id' },

  // -- Replenishment 2022-11-07 ------------------------------------------------
  // Search endpoints are POSTs (the verb heuristic derives `create…`).
  'POST /replenishment/2022-11-07/sellingPartners/metrics/search': { name: 'get_selling_partner_metrics' },
  'POST /replenishment/2022-11-07/offers/metrics/search': { name: 'list_offer_metrics' },
  'POST /replenishment/2022-11-07/offers/search': { name: 'list_offers' },

  // -- Services v1 -------------------------------------------------------------
  'POST /service/v1/serviceJobs/{serviceJobId}/appointments': { name: 'add_appointment_for_service_job_by_service_job_id' },
  'POST /service/v1/serviceJobs/{serviceJobId}/appointments/{appointmentId}': { name: 'reschedule_appointment_for_service_job_by_service_job_id' },

  // -- Vendor Direct Fulfillment Shipping 2021-12-28 ---------------------------
  'POST /vendor/directFulfillment/shipping/2021-12-28/shippingLabels': { name: 'submit_shipping_label_request' },
  'POST /vendor/directFulfillment/shipping/2021-12-28/shippingLabels/{purchaseOrderNumber}': { name: 'create_shipping_labels' },

  // The petstore fixtures (tests/petstore_sdk) need no hints: GET /orders and GET /pets both resolve to list_*.
};
