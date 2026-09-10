# Plan: spec-driven Python SDK for Amazon SP-API (`spapi`)

Step 1 of the build process: inventory of the pinned Amazon models and the design
decisions that follow from it. Everything below was measured against
`spec/selling-partner-api-models` at the commit in `spec/PINNED_COMMIT`
(`3659f96867bf`, "SP-API August 2026 Release (Fix)", 2026-08-26). The numbers are
reproducible with `python scripts/spec_inventory.py` and the API table with
`python scripts/spec_naming.py`.

Implementation starts after this plan is approved. Items marked **DECISION** are
the ones where I picked a default that you may want to change.

---

## 1. Headline numbers

| | |
|---|---|
| Spec files (`models/**/*.json`) | 67, all Swagger 2.0 (no OpenAPI 3 in the repo) |
| Distinct APIs after naming rule | 55 (12 APIs ship two or three versions) |
| Operations | 373, every one has an `operationId` |
| Schema definitions | 2,498 total, 1,908 distinct names |
| Definition names reused across APIs | 178, of which 172 have *different* shapes per API |
| Operations with a parseable rate-limit table | 300 of 373 (73 logged as unparseable) |
| Operations with static sandbox examples | 293 of 373 (925 request/response pairs) |
| Operations detected as paginated by the heuristic | 55 confirmed, 14 ambiguous (resolved by plugin overrides, see §8) |
| Notification payload schemas (`schemas/notifications`) | 23 JSON Schema draft-07 files |
| Feed / report schemas | 3 feed schemas (draft-07) + 22 report schemas; `schemas/data-kiosk` is GraphQL (out of scope) |

## 2. Decisions that need your approval

1. **DECISION – distribution name.** `spapi` on PyPI is taken by an unrelated
   package (jakksoft.com client, last release 2021). Proposal: keep the PyPI
   distribution `amzn-selling-partner` (already published, versions continue from
   0.1.9 → 0.2.0) and use `spapi` as the *import* name, with `amzn_selling_partner`
   kept as a compatibility package. README will say `pip install amzn-selling-partner`
   / `amzn-selling-partner[aiohttp]` and `import spapi`. If you can obtain the
   `spapi` PyPI name, only `pyproject.toml` changes.
2. **DECISION – Python floor 3.12.** The current package advertises 3.10–3.13; the
   new one is 3.12+ as requested (needed for `asyncio.timeout`, PEP 695 generics and
   the `frozen=True, slots=True` dataclass performance path). CI matrix becomes
   3.12 / 3.13. Recorded in `MIGRATION.md`.
3. **DECISION – drop AWS SigV4 / boto3.** SP-API stopped requiring AWS Signature V4
   in 2023; the current `ClientSessionAuth` still assumes an IAM role and signs every
   request. The new auth is LWA-only (`x-amz-access-token`). `boto3`,
   `requests_aws4auth` and `requests` are removed from runtime dependencies. The
   `AWS_*` constructor arguments of the compatibility clients are accepted and
   ignored with a `DeprecationWarning`. Recorded in `MIGRATION.md`.
4. **DECISION – resource grouping default is "per spec file".** Tags are unusable
   as a grouping key for Amazon (see §5), so `client.orders.v0.get_orders()` is the
   shape. Tag/path-prefix grouping stays available as core options for other APIs.
5. **DECISION – models are namespaced per API version, never global.** `Error`
   alone has 19 different shapes across 51 APIs (§4). Model access is
   `client.orders.v0.models.Order`; stubs mirror that.
6. **DECISION – string formats.** `date-time` → `datetime.datetime`; `date` →
   `datetime.date`; `byte` → `bytes` (base64); everything else (`PDF`, `PNG`, `ZPL`,
   `ip`, `boolean`, `[A-Z]{2}`, `application/pdf`, `dateTime`) stays `str`.
   `Decimal`/`BigDecimal` definitions are plain strings in the spec and stay `str`
   (no coercion, no validators). Note the sandbox data itself violates `date-time`
   in a few places (§9.9) so `date-time` parsing is lenient (pydantic default), not
   strict.
7. **DECISION – internal / sandbox-only operations stay exposed.** 16 operations
   carry `x-amzn-api-internal` (marker only, in `fulfillmentInbound_2024-03-20`) and
   9 responses carry `x-amzn-api-sandbox-only`. They are compiled like everything
   else and the vendor extension is preserved on `CompiledOp.extensions`; the plugin
   does not hide them.
8. **DECISION – duplicate `linkCarrierAccount` in `shippingV2`** (PUT and POST on
   the same path, §9.2). Rule: the first occurrence in document order keeps the
   name, later ones get the HTTP method appended → `link_carrier_account` (PUT) and
   `link_carrier_account_post` (POST). Logged at load time.

## 3. APIs and versions found

Naming rule (implemented in `scripts/spec_naming.py`, later moved into
`plugins/amazon_spapi.py`):

* **API name** = file stem with its version suffix removed (`_2021-08-01`,
  `-2022-11-07`, `V2022-07-01`, `V0`/`V1`/`V2`), then camelCase → snake_case.
  The directory name is *not* used because several directories hold unrelated APIs
  (`finances-api-model` holds `finances`, `financesInvoices` and `transfers`;
  `external-fulfillment` holds three).
* **Version** = `v` + `info.version` with `-` → `_` (`v0`, `v1`, `v2`, `v2021_08_01`).
* **`latest`** = highest version, where date versions sort after integer versions
  (`orders.latest` is `v2026_01_01`, `shipping.latest` is `v2`).
* Five mechanical names get a friendlier alias from the plugin (second column).
  Both names resolve to the same compiled object.

| `client.<api>` | alias | versions (`latest` first) | spec file(s) |
|---|---|---|---|
| `aplus_content` |  | `v2020_11_01` | `aplus-content-api-model/aplusContent_2020-11-01.json` |
| `app_integrations` | `application_integrations` | `v2024_04_01` | `application-integrations-api-model/appIntegrations-2024-04-01.json` |
| `application` |  | `v2023_11_30` | `application-management-api-model/application_2023-11-30.json` |
| `awd` | `amazon_warehousing_and_distribution` | `v2024_05_09` | `amazon-warehousing-and-distribution-model/awd_2024-05-09.json` |
| `catalog_items` |  | `v2022_04_01`, `v2020_12_01`, `v0` | `catalog-items-api-model/catalogItems_2022-04-01.json`, `catalog-items-api-model/catalogItems_2020-12-01.json`, `catalog-items-api-model/catalogItemsV0.json` |
| `customer_feedback` |  | `v2024_06_01` | `customer-feedback-api-model/customerFeedback_2024-06-01.json` |
| `data_kiosk` |  | `v2023_11_15` | `data-kiosk-api-model/dataKiosk_2023-11-15.json` |
| `definitions_product_types` | `product_type_definitions` | `v2020_09_01` | `product-type-definitions-api-model/definitionsProductTypes_2020-09-01.json` |
| `delivery_shipment_invoice` |  | `v2022_07_01` | `delivery-by-amazon/deliveryShipmentInvoiceV2022-07-01.json` |
| `easy_ship` |  | `v2022_03_23` | `easy-ship-model/easyShip_2022-03-23.json` |
| `external_fulfillment_inventory` |  | `v2024_09_11` | `external-fulfillment/externalFulfillmentInventory_2024-09-11.json` |
| `external_fulfillment_returns` |  | `v2024_09_11` | `external-fulfillment/externalFulfillmentReturns_2024-09-11.json` |
| `external_fulfillment_shipments` |  | `v2024_09_11` | `external-fulfillment/externalFulfillmentShipments_2024-09-11.json` |
| `fba_inbound` | `fba_inbound_eligibility` | `v1` | `fba-inbound-eligibility-api-model/fbaInbound.json` |
| `fba_inventory` |  | `v1` | `fba-inventory-api-model/fbaInventory.json` |
| `feeds` |  | `v2021_06_30` | `feeds-api-model/feeds_2021-06-30.json` |
| `finances` |  | `v2024_06_19`, `v0` | `finances-api-model/finances_2024-06-19.json`, `finances-api-model/financesV0.json` |
| `finances_invoices` |  | `v2026_06_25` | `finances-api-model/financesInvoices_2026-06-25.json` |
| `fulfillment_inbound` |  | `v2024_03_20`, `v0` | `fulfillment-inbound-api-model/fulfillmentInbound_2024-03-20.json`, `fulfillment-inbound-api-model/fulfillmentInboundV0.json` |
| `fulfillment_outbound` |  | `v2026_07_04`, `v2020_07_01` | `fulfillment-outbound-api-model/fulfillmentOutbound_2026-07-04.json`, `fulfillment-outbound-api-model/fulfillmentOutbound_2020-07-01.json` |
| `invoices_api_model` | `invoices` | `v2024_06_19` | `invoices-api-model/InvoicesApiModel_2024-06-19.json` |
| `listings_items` |  | `v2021_08_01`, `v2020_09_01` | `listings-items-api-model/listingsItems_2021-08-01.json`, `listings-items-api-model/listingsItems_2020-09-01.json` |
| `listings_restrictions` |  | `v2021_08_01` | `listings-restrictions-api-model/listingsRestrictions_2021-08-01.json` |
| `merchant_fulfillment` |  | `v0` | `merchant-fulfillment-api-model/merchantFulfillmentV0.json` |
| `messaging` |  | `v1` | `messaging-api-model/messaging.json` |
| `notifications` |  | `v1` | `notifications-api-model/notifications.json` |
| `orders` |  | `v2026_01_01`, `v0` | `orders-api-model/orders_2026-01-01.json`, `orders-api-model/ordersV0.json` |
| `product_fees` |  | `v0` | `product-fees-api-model/productFeesV0.json` |
| `product_pricing` |  | `v2022_05_01`, `v0` | `product-pricing-api-model/productPricing_2022-05-01.json`, `product-pricing-api-model/productPricingV0.json` |
| `promotions` |  | `v2025_12_01` | `promotions-api-model/promotions_2025-12-01.json` |
| `replenishment` |  | `v2022_11_07` | `replenishment-api-model/replenishment-2022-11-07.json` |
| `reports` |  | `v2021_06_30` | `reports-api-model/reports_2021-06-30.json` |
| `sales` |  | `v1` | `sales-api-model/sales.json` |
| `seller_wallet` |  | `v2024_03_01` | `seller-wallet-api-model/sellerWallet_2024-03-01.json` |
| `sellers` |  | `v1` | `sellers-api-model/sellers.json` |
| `services` |  | `v1` | `services-api-model/services.json` |
| `shipment_invoicing` |  | `v0` | `shipment-invoicing-api-model/shipmentInvoicingV0.json` |
| `shipping` |  | `v2`, `v1` | `shipping-api-model/shippingV2.json`, `shipping-api-model/shipping.json` |
| `solicitations` |  | `v1` | `solicitations-api-model/solicitations.json` |
| `supply_sources` |  | `v2020_07_01` | `supply-sources-api-model/supplySources_2020-07-01.json` |
| `tokens` |  | `v2021_03_01` | `tokens-api-model/tokens_2021-03-01.json` |
| `tracking` |  | `v2026_01_30` | `tracking-api-model/tracking_2026-01-30.json` |
| `transfers` |  | `v2024_06_01` | `finances-api-model/transfers_2024-06-01.json` |
| `uploads` |  | `v2020_11_01` | `uploads-api-model/uploads_2020-11-01.json` |
| `vehicles` |  | `v2024_11_01` | `vehicles-api-model/vehicles_2024-11-01.json` |
| `vendor_direct_fulfillment_inventory` |  | `v1` | `vendor-direct-fulfillment-inventory-api-model/vendorDirectFulfillmentInventoryV1.json` |
| `vendor_direct_fulfillment_orders` |  | `v2021_12_28`, `v1` | `vendor-direct-fulfillment-orders-api-model/vendorDirectFulfillmentOrders_2021-12-28.json`, `vendor-direct-fulfillment-orders-api-model/vendorDirectFulfillmentOrdersV1.json` |
| `vendor_direct_fulfillment_payments` |  | `v1` | `vendor-direct-fulfillment-payments-api-model/vendorDirectFulfillmentPaymentsV1.json` |
| `vendor_direct_fulfillment_sandbox_data` |  | `v2021_10_28` | `vendor-direct-fulfillment-sandbox-test-data-api-model/vendorDirectFulfillmentSandboxData_2021-10-28.json` |
| `vendor_direct_fulfillment_shipping` |  | `v2021_12_28`, `v1` | `vendor-direct-fulfillment-shipping-api-model/vendorDirectFulfillmentShipping_2021-12-28.json`, `vendor-direct-fulfillment-shipping-api-model/vendorDirectFulfillmentShippingV1.json` |
| `vendor_direct_fulfillment_transactions` |  | `v2021_12_28`, `v1` | `vendor-direct-fulfillment-transactions-api-model/vendorDirectFulfillmentTransactions_2021-12-28.json`, `vendor-direct-fulfillment-transactions-api-model/vendorDirectFulfillmentTransactionsV1.json` |
| `vendor_invoices` |  | `v1` | `vendor-invoices-api-model/vendorInvoices.json` |
| `vendor_orders` |  | `v1` | `vendor-orders-api-model/vendorOrders.json` |
| `vendor_shipments` |  | `v1` | `vendor-shipments-api-model/vendorShipments.json` |
| `vendor_transaction_status` |  | `v1` | `vendor-transaction-status-api-model/vendorTransactionStatus.json` |

Operation method names are `snake_case(operationId)`: `getOrders` →
`get_orders`, `GetShipmentDetails` → `get_shipment_details`,
`getMyFeesEstimateForSKU` → `get_my_fees_estimate_for_sku`. Parameter names keep the
spec's casing as the wire alias and expose snake_case keyword arguments
(`MarketplaceIds` → `marketplace_ids=`, `x-amzn-shipping-business-id` →
`x_amzn_shipping_business_id=`); the compiled signature stores both.

## 4. Model naming and collisions

* 178 definition names appear in more than one API and 172 of those differ
  structurally. Worst offenders: `Error` (51 APIs / 19 shapes), `ErrorList` (51 / 24),
  `Address` (17 / 20), `Pagination` (14 / 15), `Item` (11 / 13), `Money` (10 / 10).
* Therefore: **one model namespace per (API, version)**, memoised by
  `(spec hash, schema name)`. There is no cross-API sharing, not even for `Error`;
  a shared error *protocol* lives in the runtime (`APIStatusError.body` is the
  decoded per-API `ErrorList` when the response parses, else the raw JSON).
* Within one spec file definition names are unique, so the pydantic class name is
  the definition name unchanged (`Order`, `OrdersList`). Inline object schemas
  (24 occurrences, all nested `properties` without a definition) are named
  `<Parent><FieldName>` (`ItemSearchResultsPagination`); anonymous array items get
  `<Parent>Item`.
* `__module__` of generated classes is set to
  `spapi.models.<api>.<version>` so pickling, `repr` and stubs agree; the actual
  attribute lives on the compiled resource (`client.orders.v0.models`).
* Model name that is also a Python keyword or shadows `BaseModel` attributes
  (`schema`, `copy`, `json`, `dict`, `validate` as *field* names occur in a few
  APIs) → field gets a trailing underscore with the original as alias, which
  `populate_by_name=True` plus the alias generator already handles.

## 5. Swagger 2.0 → IR mapping

| Swagger 2.0 construct | Occurrences | IR (`spec/ir.py`) |
|---|---|---|
| `host` / `basePath` / `schemes` | all files; two files have a non-NA host (`shippingV2` → EU, sandbox-data → sandbox NA); `basePath` is `/` in 2 files, absent elsewhere | one `Server(url=f"{scheme}://{host}{basePath.rstrip('/')}")`; Amazon plugin replaces servers with the regional table (§10) |
| `paths.<p>.<method>` | 373 | `Operation(method, path, operation_id, tags, summary, description, parameters, request_body, responses, extensions, deprecated)` |
| `paths.<p>.parameters` (path-level) | 0 in Amazon, supported anyway | merged into each operation, operation-level wins on `(name, in)` |
| `in: path` (255) / `query` (661) / `header` (41) | | `Parameter(name, location, required, schema, style, explode, extensions)`; `collectionFormat csv` → `style=form, explode=False`; `multi` (2 params in `fulfillmentInbound_2024-03-20`) → `explode=True`; `ssv`/`tsv`/`pipes` → `spaceDelimited`/`tabDelimited`(custom)/`pipeDelimited` |
| `in: body` (148) + `consumes` | all `application/json` | `RequestBody(required, content={"application/json": Schema}, description)` |
| `in: formData` / `type: file` | 0 | supported in IR (`multipart/form-data`), no Amazon usage |
| `produces` | all JSON (no non-JSON responses found) | `Response.content = {"application/json": Schema}`; no `schema` → `content = {}` and the op returns `None` (35 × 204, `cancelFeed`/`cancelReport`/`cancelReportSchedule` 200 without schema) |
| `responses.<code>` | 200 (287), 201 (18), 202 (40), 204 (35), 207 (1); errors 400…503 | one `Response` per code, `default` kept; the compiler builds a `TypeAdapter` per 2xx with a schema and a shared error adapter |
| `responses.<code>.headers` | `x-amzn-RateLimit-Limit`, `x-amzn-RequestId` | `Response.headers: dict[str, Schema]`; runtime reads `x-amzn-RequestId` into `APIStatusError.request_id` |
| `definitions` | 2,498 | `Document.schemas: dict[str, Schema]`; `#/definitions/X` and `#/components/schemas/X` both resolve to it |
| `$ref` | 6,826, all local `#/definitions/...`; no external/relative refs in Amazon | resolved at load; relative-file refs supported for the fixtures/other specs |
| `allOf` (27) | mostly `AplusResponse` composition | `Schema(all_of=[...])`; compiler merges properties/required into one model (parents first) |
| `oneOf` / `anyOf` / `discriminator` / `x-nullable` | 0 in Amazon | supported in IR and compiler (exercised by the OpenAPI 3.1 fixture) |
| `additionalProperties` (28) | `{type: string}` (9), `{}` (8), `true` (7), `$ref` (4) | `Schema.additional_properties: Schema \| bool`; typed as `dict[str, T]` when the schema has no `properties`, otherwise `extra="allow"` (already the default) |
| `enum` (570, all strings) | | `Literal[...]`; `x-docgen-enum-table-extension` kept in `extensions` |
| `format` | `date-time` 320, `int32` 47, `int64` 43, `double` 52, `float` 13, `date` 8, `byte` 2, non-standard 26 | see §2.6 |
| `required` (2,049) | | non-required fields are `T \| None = None` |
| `x-*` on operations/responses/params/root | `x-amzn-api-sandbox` (767, at *response* level), `x-amzn-api-sandbox-only` (9), `x-amzn-api-internal` (16), `x-amazon-spds-sandbox-behaviors` (9, `vendorShipments` only), `x-amazon-spds-greedy-path-parameter` (1, `uploads` `{resource}`), `x-example`/`x-examples`, `x-components` (empty) | preserved verbatim as `extensions: Mapping[str, Any]` on every node; plugin consumes the ones it knows |

OpenAPI 3.x documents map onto the same IR directly (`servers`, `requestBody`,
`components.schemas`, `content`); the loader normalises both into one shape so
the compiler never sees the source format.

## 6. Tags and paths → resources

Tags are not a usable grouping key for Amazon:

* 5 files have no tags at all (`finances*`, `transfers`).
* Tags are mostly one-per-file and equal to the API name (`orders` → `ordersV0` +
  `shipment`; `listingsItems` → `listings`).
* Some tags contain spaces (`Transfer Preview`, `Transfer Schedule`) or are
  sub-features (`fulfillmentOutbound_2026-07-04`: `fulfillmentOrders`,
  `fulfillmentPreviews`, `offers`).

Chosen default: **one resource per spec file** → `client.<api>.<version>` is a
`Resource` whose methods are the operations. `Resource` construction is
configurable (`group_by="file" | "tag" | "path_prefix"`) in the core and the
Amazon plugin selects `"file"`. `client.<api>.latest` is an alias attribute.
`__dir__` on the client lists API names (+ aliases); on an API it lists versions
and `latest`; on a resource it lists operation methods and `models`.

## 7. Sandbox examples

* **Static examples** are stored at the *response* level:
  `responses.<code>.x-amzn-api-sandbox.static[] = {request: {parameters: {<name>: {value}}, body?}, response: <json>}`.
  293 operations / 925 pairs across 60 files. Both the 2xx pairs and error pairs
  (e.g. 400 examples) are present; the runner will use every pair and assert the
  status code and decoded body.
* **Dynamic markers** (`x-amzn-api-sandbox: {dynamic: {}}`) sit at operation
  level on 28 operations (`shipping` v1/v2, all `vendorDirectFulfillment*_2021-12-28`,
  sandbox-data). They carry no data; the runner skips them.
* `vendorShipments` uses a different key, `x-amazon-spds-sandbox-behaviors`, with
  the same `{request, response}` shape → the plugin normalises it into the same
  list.
* All 10 `orders_v0` operations have static examples (31 pairs), as do all 5
  `listings-items_2021-08-01` operations (14 pairs), so step 3's sandbox tests cover
  both target APIs completely.
* Files with no static examples at all (9): `aplusContent_2020-11-01`,
  `fbaInventory`, `fulfillmentOutbound_2020-07-01`, `fulfillmentOutbound_2026-07-04`,
  `uploads_2020-11-01`, and the four `vendorDirectFulfillment*_2021-12-28` /
  sandbox-data files that only carry dynamic markers. `shippingV2` has static
  data for 1 of its 20 operations. Those operations are covered by the
  MockTransport suite (synthetic bodies from the schema) instead.

## 8. Rate limits

* Format A (303 ops): `| Rate (requests per second) | Burst |` / `| ---- | ---- |` /
  `| 0.0167 | 20 |` inside a `**Usage Plan:**` section of the description.
* Format B (2 ops, `definitionsProductTypes_2020-09-01`):
  `| Plan type | Rate (requests per second) | Burst |` with a `Default` row and a
  `Selling partner specific | Variable | Variable` row → parse the `Default` row.
* 1 op (`listPrepDetails`) has the table with placeholder values `| n | n |` → logged.
* 72 ops have no table at all: `awd` (4 replenishment ops), all 7 `customerFeedback`,
  all 13 `externalFulfillment*`, `fbaInventory` sandbox ops (3), `financesInvoices`
  (2), `fulfillmentInbound_2024-03-20` self-ship appointment ops (4),
  `fulfillmentOutbound` (3), all 10 `InvoicesApiModel`, `messaging.sendInvoice`,
  `definitionsProductTypes` (2, format B), `promotions` (3), all 12 `sellerWallet`,
  all 6 `supplySources`, `tracking`, `vehicles`, sandbox-data (2).
* Result: **300 parsed, 73 unparseable and logged, never guessed.** Operations
  without a `rate_limit` annotation run unthrottled unless the client sets a
  default bucket; the 429 handler still honours `x-amzn-RateLimit-Limit`.

## 9. Pagination

Heuristic in `compile/operations.py` (API-agnostic):

1. A query parameter whose name, case-insensitively, is one of
   `nextToken`, `pageToken`, `paginationToken`.
2. A string field with the same name *or* named `nextToken` (case-insensitive) in
   the first 2xx schema at one of: top level, `payload`, `pagination`,
   `payload.pagination`.
3. Exactly one array-typed field in the token's container, or, if that container
   has none, in its parent (`payload` or top level), ignoring a field named
   `errors`.

Against the pinned specs this yields **55 confirmed** (`getOrders`, `getOrderItems`,
`getOrderItemsBuyerInfo`, `searchOrders`, `getReports`, `getFeeds`, `searchCatalogItems` ×2, `searchListingsItems`,
`getSubscriptions`, `getQueries`, 14 `fulfillmentInbound_2024-03-20` list ops,
`listInboundShipments`/`listInventory`/`listOutbounds`/`listReplenishmentOrders`,
finances/transfers list ops, `getInvoices`/`getInvoicesExports`, …) and
**14 ambiguous**, all handled by plugin overrides:

| Operation | Why ambiguous | Plugin override |
|---|---|---|
| `vendorOrders.getPurchaseOrders`, `getPurchaseOrdersStatus`; `vendorShipments.GetShipmentDetails`, `GetShipmentLabels`; `vendorDirectFulfillmentShippingV1.getShippingLabels`/`getCustomerInvoices`/`getPackingSlips`; `vendorDirectFulfillmentOrdersV1.getOrders` | token at `payload.pagination.nextToken`, array at `payload.<x>` — covered once rule 3's "parent" step is implemented, listed here because the survey script only looked one level deep | none needed after the heuristic fix; kept in the plugin's expected list |
| `aplusContent.searchContentDocuments`, `listContentDocumentAsinRelations`, `searchContentPublishRecords` | request param `pageToken`, response field `nextPageToken` (different name) | `Pagination(next_token_path="nextPageToken", next_token_param="pageToken", items_path=...)` |
| `services.getServiceJobs` | `pageToken` vs `payload.nextPageToken` | same shape override |
| `fulfillmentInbound_2024-03-20.getSelfShipAppointmentSlots` | token in `pagination`, but the data is an object (`selfShipAppointmentSlotsAvailability.slots`) | `items_path="selfShipAppointmentSlotsAvailability.slots"` |
| `promotions.getSelection` | `paginationToken` param; token nested at `selection.selectionDetails.pagination` | `items_path="selection.selectionDetails.items"` |
| `financesV0.listFinancialEvents*` (3 ops) | `payload.FinancialEvents` is an object of ~30 event arrays, not one array | `items_path="payload.FinancialEvents"` with `items_is_object=True` → each page yields one `FinancialEvents` object |
| `fbaInventory.getInventorySummaries` | token at `pagination.nextToken` (top level), array at `payload.inventorySummaries` | covered by rule 3 once `errors` is ignored; explicit override kept |

Requested overrides that also carry `drop_params_on_next`:
`getOrders` (v0), `getReports`, `getFeeds`, `searchCatalogItems` (both versions),
plus the ops whose `nextToken` description says the other parameters must be
omitted: `getQueries` (Data Kiosk), `getInventorySummaries`, `getSubscriptions`.
The plugin lists these explicitly (not regex-detected at runtime) and has a test
asserting the list against the descriptions so a spec bump that changes the
wording is noticed.

Token shapes handled by `SyncPage`/`AsyncPage`: `payload.NextToken`,
`payload.nextToken`, `pagination.nextToken`, `payload.pagination.nextToken`,
top-level `nextToken`, and any explicit `next_token_path`.

## 10. Spec irregularities found

1. No missing `operationId`s (0 / 373).
2. `shippingV2.linkCarrierAccount` is defined twice (PUT and POST,
   `/shipping/v2/carrierAccounts/{carrierId}`) → §2.8.
3. 32 `operationId`s are reused across files (`getOrder` ×5, `getShipment` ×4,
   `submitInvoice` ×3, …). Harmless with per-file resources.
4. `host` differs per file: `shippingV2` says `sellingpartnerapi-eu.amazon.com`,
   `vendorDirectFulfillmentSandboxData` says `sandbox.sellingpartnerapi-na.amazon.com`.
   The plugin ignores `host` entirely and uses its regional table
   (NA/EU/FE × production/sandbox).
5. `basePath: "/"` in `dataKiosk` and `reports` → normalised to `""` so URLs do not
   get `//`.
6. `uploads.createUploadDestinationForResource` marks `{resource}` with
   `x-amazon-spds-greedy-path-parameter: true` → the path serializer must not
   percent-encode `/` for that parameter (`allowReserved`-like flag on `Parameter`,
   set by the plugin from the extension).
7. 26 non-standard `format` values (`PDF`, `PNG`, `ZPL`, `application/pdf`,
   `boolean`, `dateTime`, `ip`, `[A-Z]{2}`) → treated as `str`.
8. Property names that collide with `BaseModel` attributes (`schema`, `copy`,
   `json`, `dict`, `validate`, `model_config`-style names) exist in a handful of
   APIs (`definitionsProductTypes` has `schema`) → suffixed field names with alias.
9. Sandbox example data violates its own schema in places: `ordersV0`
   `OrdersList.CreatedBefore` is `"1.569521782042E9"` in the example while the
   field is described as ISO 8601 (it has no `format`, so it decodes as `str`);
   `PurchaseDate` is `"1970-01-19T03:58:30Z"` (valid). The sandbox runner will
   report any example that fails validation as an `xfail` with the reason, not
   hide it.
10. Empty `x-components: {}` at the root of `fulfillmentInbound_2024-03-20`
    (ignored).
11. Tags with spaces in `sellerWallet` (`Transfer Preview`) — irrelevant under
    per-file grouping, snake_cased if tag grouping is selected.
12. `vendorShipments` uses `x-amazon-spds-sandbox-behaviors` instead of
    `x-amzn-api-sandbox` (§7).
13. Header parameters exist on 41 operations (`x-amzn-shipping-business-id` on all
    20 `shippingV2` ops, `x-amzn-fulfillment-service-id`, `x-amzn-IdempotencyKey`,
    `x-amzn-idempotency-token`, `destAccountDigitalSignature`,
    `amountDigitalSignature`, `Accept-Language`, `locale`) → exposed as keyword
    arguments; the compiled header serializer is separate from the default headers
    computed at client init, so there is still no per-request dict merging (the
    per-op header list is appended to a tuple of default header pairs).
14. Grantless operations are documented only in prose: the 7 destination /
    subscription-by-id ops in `notifications` plus
    `application.rotateApplicationClientSecret`. The plugin keeps an explicit
    table (`sellingpartnerapi::notifications`,
    `sellingpartnerapi::client_credential:rotation`) with a test that greps the
    descriptions for "grantless" and fails if the set drifts.
15. Restricted Data Token operations are not marked in the specs: only
    `tokens.createRestrictedDataToken` mentions RDTs at all. The plugin therefore
    ships a hand-maintained table keyed by `(api, version, operationId)` with the
    `dataElements` each entry accepts. Initial content, from the Tokens API use-case
    guide's "restricted operations" list (the developer-docs site is not reachable
    from this environment, so **please verify this table when reviewing**):

    | API | Operations | Notes |
    |---|---|---|
    | `orders.v0` | `getOrders`, `getOrder`, `getOrderItems` | RDT only when `dataElements` requests `buyerInfo` / `shippingAddress` (`buyerTaxInformation` for items) |
    | `orders.v0` | `getOrderBuyerInfo`, `getOrderAddress`, `getOrderItemsBuyerInfo`, `getOrderRegulatedInfo` | always |
    | `orders.v2026_01_01` | `searchOrders`, `getOrder` | same `dataElements` rule as v0 (to verify) |
    | `reports.v2021_06_30` | `getReportDocument` | only for the restricted report types listed in the guide; the plugin keeps that list too |
    | `merchant_fulfillment.v0` | `createShipment`, `getShipment`, `cancelShipment` | always |
    | `shipping.v1` | `createShipment`, `getShipment`, `cancelShipment`, `purchaseLabels`, `retrieveShippingLabel`, `purchaseShipment` | always |
    | `vendor_direct_fulfillment_orders.v1` / `.v2021_12_28` | `getOrders`, `getOrder` | always |
    | `vendor_direct_fulfillment_shipping.v1` / `.v2021_12_28` | `getShippingLabel(s)`, `getCustomerInvoice(s)`, `getPackingSlip(s)` | always |
    | `easy_ship.v2022_03_23` | `createScheduledPackage`, `getScheduledPackage`, `updateScheduledPackages`, `createScheduledPackageBulk` | to verify |

    Each entry records the source URL and the date it was checked; a unit test
    asserts every referenced operation still exists in the pinned specs.

## 11. Existing code and migration

Current package `amzn_selling_partner` (v0.1.9) covers only `vendor.orders` (v1,
`getPurchaseOrders`, `getPurchaseOrder`) and `reports` (2021-06-30, `createReport`,
`getReports`, `getReport`, `getReportDocument`, document download helpers) with
`requests` + `requests_aws4auth` + `boto3` + pydantic 1.

Public entry points kept as aliases over the new runtime:

| Old | New home | Status |
|---|---|---|
| `amzn_selling_partner.client.BaseClient` | `spapi.SellingPartner` | thin subclass, same kwargs (AWS ones ignored with warning) |
| `amzn_selling_partner.client.SellingPartnerRegion` | `spapi.plugins.amazon_spapi.Region` | alias, same members and `api_endpoint` / `api_sandbox_endpoint` properties; `region_name` kept |
| `amzn_selling_partner.vendor.orders.Client` | `client.vendor_orders.v1` | wrapper keeping `get_purchase_orders(query=...)` (auto-pages) and `get_purchase_order(id)` |
| `amzn_selling_partner.reports.Client` | `client.reports.v2021_06_30` + document helpers | wrapper keeping all 7 public methods; `pages_limit` kept |
| `amzn_selling_partner.vendor.orders.models.*`, `reports.models.*` | `client.vendor_orders.v1.models`, `client.reports.v2021_06_30.models` | **breaking**: pydantic 2 classes (`.dict()` → `.model_dump()`), enums become `Literal` strings, `GetPurchaseOrdersQuery`/`GetReportsQuery` request models replaced by keyword arguments (kept as `TypedDict`s for the wrappers) |
| `amzn_selling_partner.utils.date`, `utils.file` | unchanged | kept |
| `amzn_selling_partner.__version__` | unchanged | kept |

`MIGRATION.md` records: Python 3.12+, dependency changes, LWA-only auth (env var
names `SELLING_PARTNER_APP_*` still honoured), exceptions (`requests.HTTPError` →
`spapi.APIStatusError`), pydantic 2, the `respx`/`pytest-httpx` note with the
`httpx2.MockTransport` pattern, and the report-throttling change (the old
`get_reports` slept `x-amzn-RateLimit-Limit * 100` seconds after every call; the
new client uses the token bucket).

## 12. Package layout (as specified) and implementation order

```
src/spapi/
  __init__.py            # lazy re-exports; imports build no models
  client.py              # Client / AsyncClient / SellingPartner / AsyncSellingPartner
  stubgen.py             # CLI: python -m spapi.stubgen
  sandbox_tests.py       # x-amzn-api-sandbox -> MockTransport runner
  spec/   ir.py loader.py swagger2.py openapi3.py refs.py cache.py
  compile/ models.py operations.py resources.py naming.py
  runtime/ _base_client.py _transports.py _json.py _errors.py _pagination.py
           _auth.py _throttle.py _stream.py _types.py (NotGiven, Omit, RequestOptions)
  plugins/ __init__.py (Plugin protocol) amazon_spapi.py  (+ _amazon/ rate_limits.py,
           auth.py, rdt.py, regions.py, pagination.py, documents.py, notifications.py)
src/amzn_selling_partner/   # compatibility package
spec/selling-partner-api-models (submodule), spec/PINNED_COMMIT
tests/fixtures/{petstore_oas31.yaml, petstore_swagger2.json} + symlinked Amazon specs
benchmarks/bench.py, stubs/ (generated .pyi, CI-checked)
docs/PLAN.md (this file), docs/UPDATING_SPECS.md, MIGRATION.md, README.md
```

Order, with the check-point after each: `pytest`, `pyright --strict` on
hand-written code, benchmark numbers in the PR description.

1. `spec/` loader + IR + pickle cache → tests on the two small fixtures, then all
   67 Amazon files load (report parse time per file).
2. `compile/models.py` → tests for recursion, enums, unions, additionalProperties,
   nullable, date/datetime, binary; then build every Amazon model namespace and
   report build time per API (targets: < 50 ms from cache, < 300 ms cold).
3. `compile/operations.py` + `resources.py` → serializer/body/NotGiven/TypeError
   tests, Hypothesis fuzzing of serializers, sync/async signature-equality test.
4. `runtime/` + `client.py` → MockTransport suite over every fixture op, retries,
   timeouts, cancellation, pool release, streaming.
5. `orders` + `listings_items` end to end (sandbox-driven tests for all 15 ops,
   multi-page walks), then load all APIs and report numbers.
6. Amazon plugin: rate limits, LWA auth (single-flight), RDT, throttle, regions,
   pagination overrides, documents, notification models.
7. `stubgen.py` + `benchmarks/bench.py` + nightly CI with 15 % threshold.
8. Compatibility package, `MIGRATION.md`, README, `docs/UPDATING_SPECS.md`.

## 13. Performance design notes (what "as cheap as hand-written" means here)

* `CompiledOp` is a frozen slotted dataclass holding: `method`, `url_template`
  (a `str.format`-free callable built from pre-split literal segments), tuples of
  `(python_name, wire_name, serializer)` for path/query/header, `body_encoder`
  (`TypeAdapter.dump_json(by_alias=True, exclude_none=True)` bound method or
  `pydantic_core.to_json`), `success: tuple[(status, TypeAdapter)]`,
  `error_adapter`, `signature`, `rate_limit`, `pagination`, `extensions`.
* The generated method body is one function (`def op(self, *, **kw)`) created
  once via `functools.partial` around a shared `_call` that takes the
  `CompiledOp`; `__signature__`, `__name__`, `__doc__`, `__qualname__` are set on
  it. No `exec` of generated source is needed; the benchmark (d) will show whether
  a `types.FunctionType` build is required to stay within 10 %.
* Unexpected keyword → `TypeError` comes from a precomputed `frozenset` check,
  not `inspect.Signature.bind`.
* Default headers are a `tuple[tuple[str, str], ...]` computed at init; per-op
  headers extend it by tuple concatenation (no dict merge).
* Request options per call use a frozen slotted dataclass (`RequestOptions`),
  created only when the caller passes `timeout=`, `headers=`, `raw=` or
  `paginate=`; otherwise the shared default instance is used.
