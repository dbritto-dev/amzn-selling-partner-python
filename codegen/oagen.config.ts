/**
 * oagen configuration: the plugin (the `python` emitter) plus this
 * repository's spec policy. `npm run spec:build` writes the merged OpenAPI 3
 * document (`.build/openapi.yml`), then
 * `npm run sdk:generate -- --spec .build/openapi.yml --namespace Client`
 * runs `oagen generate` with this config (`npm run regenerate` does both, plus
 * the petstore fixtures and ruff).
 */
import type { OagenConfig } from '@workos/oagen';
import { ALIASES } from './src/amazon.js';
import type { JsonObject } from './src/convert.js';
import { myEmittersPlugin } from './src/plugin.js';
import { schemaNameTransform, transformSpec } from './src/transform.js';

const config: OagenConfig = {
  ...myEmittersPlugin,

  // Pre-IR fixes for the Amazon files (alias schemas, inline objects, name protection).
  transformSpec: (doc) => transformSpec(doc as unknown as JsonObject) as never,
  schemaNameTransform,
  // Keep operationIds verbatim: they key Amazon's documentation, the RDT tables and the sandbox examples.
  operationIdTransform: (id) => id,

  // Method names come from oagen's resolver; these are the operations whose derived
  // names collide within their service (`npm run sdk:resolve -- --spec .build/openapi.yml`).
  operationHints: {
    'POST /aplus/2020-11-01/contentDocuments': { name: 'create_content_document' },
    'POST /aplus/2020-11-01/contentDocuments/{contentReferenceKey}': { name: 'update_content_document' },
    'GET /customerFeedback/2024-06-01/items/{asin}/reviews/topics': { name: 'get_item_review_topics' },
    'GET /customerFeedback/2024-06-01/browseNodes/{browseNodeId}/reviews/topics': { name: 'get_browse_node_review_topics' },
    'GET /customerFeedback/2024-06-01/items/{asin}/reviews/trends': { name: 'get_item_review_trends' },
    'GET /customerFeedback/2024-06-01/browseNodes/{browseNodeId}/reviews/trends': { name: 'get_browse_node_review_trends' },
    'GET /customerFeedback/2024-06-01/browseNodes/{browseNodeId}/returns/topics': { name: 'get_browse_node_return_topics' },
    'GET /customerFeedback/2024-06-01/browseNodes/{browseNodeId}/returns/trends': { name: 'get_browse_node_return_trends' },
    'PUT /externalFulfillment/2024-09-11/shipments/{shipmentId}/packages/{packageId}': { name: 'update_package' },
    'PATCH /externalFulfillment/2024-09-11/shipments/{shipmentId}/packages/{packageId}': { name: 'update_package_status' },
    'GET /fba/inbound/v0/shipments/{shipmentId}/items': { name: 'get_shipment_items_by_shipment_id' },
    'GET /fba/inbound/v0/shipmentItems': { name: 'get_shipment_items' },
    'GET /fba/outbound/2020-07-01/features/inventory/{featureName}': { name: 'get_feature_inventory' },
    'GET /fba/outbound/2020-07-01/features/inventory/{featureName}/{sellerSku}': { name: 'get_feature_sku' },
    'PUT /listings/2020-09-01/items/{sellerId}/{sku}': { name: 'put_listings_item' },
    'PATCH /listings/2020-09-01/items/{sellerId}/{sku}': { name: 'patch_listings_item' },
    'PUT /listings/2021-08-01/items/{sellerId}/{sku}': { name: 'put_listings_item' },
    'PATCH /listings/2021-08-01/items/{sellerId}/{sku}': { name: 'patch_listings_item' },
    'GET /listings/2021-08-01/items/{sellerId}/{sku}': { name: 'get_listings_item' },
    'GET /listings/2021-08-01/items/{sellerId}': { name: 'search_listings_items' },
    'GET /notifications/v1/subscriptions/{notificationType}': { name: 'get_subscription' },
    'GET /notifications/v1/subscriptions/{notificationType}/{subscriptionId}': { name: 'get_subscription_by_id' },
    'POST /replenishment/2022-11-07/sellingPartners/metrics/search': { name: 'get_selling_partner_metrics' },
    'POST /replenishment/2022-11-07/offers/metrics/search': { name: 'list_offer_metrics' },
    'POST /replenishment/2022-11-07/offers/search': { name: 'list_offers' },
    'POST /service/v1/serviceJobs/{serviceJobId}/appointments': { name: 'add_appointment_for_service_job_by_service_job_id' },
    'POST /service/v1/serviceJobs/{serviceJobId}/appointments/{appointmentId}': { name: 'reschedule_appointment_for_service_job_by_service_job_id' },
    'POST /vendor/directFulfillment/shipping/2021-12-28/shippingLabels': { name: 'submit_shipping_label_request' },
    'POST /vendor/directFulfillment/shipping/2021-12-28/shippingLabels/{purchaseOrderNumber}': { name: 'create_shipping_labels' },
    // the petstore fixtures (tests/petstore_sdk): GET /orders and GET /pets both resolve to list_*
  },

  // oagen splits a service whose paths start with different segments; keep one resource per API version.
  mountRules: {
    Products: 'ProductPricingV0', // /products/pricing/v0/...
    Batches: 'ProductPricingV0', // /batches/products/pricing/v0/...
  },

  // Language-specific options (`ctx.emitterOptions` in the python emitter).
  emitterOptions: {
    python: {
      // SDK runtime policy, merged over oagen's defaults and generated into http_client.py.
      sdkBehavior: {
        retry: {
          retryableStatusCodes: [408, 429, 500, 502, 503, 504],
          maxRetries: 2,
          backoff: { initialDelay: 0.5, maxDelay: 8.0, multiplier: 2, jitterFactor: 0.5 },
        },
        timeout: { defaultTimeoutSeconds: 30, timeoutEnvVar: 'AMZN_SELLING_PARTNER_TIMEOUT' },
      },
      distribution: 'amzn_selling_partner',
      requestIdHeader: 'x-amzn-RequestId',
      rateHintHeader: 'x-amzn-RateLimit-Limit',
      greedyPathParams: ['resource'],
      serviceAliases: ALIASES,
    },
  },
};

export default config;
