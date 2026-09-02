# SP-API types and enums update proposal

## Scope

This proposal covers the implemented Reports API (`2021-06-30`) and Retail
Procurement Orders API (`vendor/orders/v1`) models. It compares the current
types with Amazon's official OpenAPI models on September 2, 2026.

## Findings and proposed changes

### 1. Make Reports report types forward-compatible

`ReportType` currently restricts requests and responses to eight vendor
report values. Amazon's Reports API model defines `reportType` as a string and
directs clients to the maintained Report Type Values catalog. For example, the
official model uses `FEE_DISCOUNTS_REPORT` and
`GET_MERCHANT_LISTINGS_ALL_DATA`, neither of which the current enum accepts.

Replace the `ReportType` annotations in `CreateReportSpecification`,
`GetReportsQuery`, and `Report` with `str`. Retain the current enum, if
desired, only as an optional convenience set rather than as validation.

### 2. Preserve arbitrary Reports options

Amazon defines `ReportOptions` as an object with string
`additionalProperties`, because valid options depend on `reportType`. The
current fixed Pydantic model can discard options other than `reportPeriod`,
`distributorView`, and `sellingProgram` when it is serialized.

Replace `ReportOptions` with a string-to-string mapping, or configure its
model to preserve arbitrary string fields. Keep the existing named options as
documented conveniences only if they do not prevent additional options from
being sent.

### 3. Do not validate marketplace IDs against a stale enum

The Reports API accepts arrays of marketplace-ID strings. The local
`MarketPlaceId` enum prevents newly supported marketplaces from being used
until this library releases an update. It also exposes Spain under the
misspelled member name `PAIN` despite having the correct value.

Use `List[str]` for Reports marketplace fields. The enum may remain as an
optional convenience type, with a correctly named `SPAIN` member and a
backward-compatible `PAIN` alias.

### 4. Support the Reports document content-encoding option

The official Reports model provides
`enableContentEncodingUrlHeader` when retrieving a report document. It allows
GZIP report URLs to return `Content-Encoding: gzip`. The current client
cannot pass this option and always manually decompresses content.

Add the optional boolean parameter to the report-document retrieval query and
client API. Specify and test the download behavior for both enabled and
disabled content encoding so content is decompressed exactly once.

### 5. Correct Vendor Orders money and quantity types

The Vendor Orders `Money.amount` schema is a decimal string, not a float, and
includes an optional weight-price `unitOfMeasure`. The present `float` type
can lose currency precision and the model omits the unit entirely. In
addition, `ItemQuantity.unitOfMeasure` has the constrained `Cases` and
`Eaches` values but is currently typed as `str`.

Introduce a `Decimal`-compatible money amount type, add a
`MoneyUnitOfMeasure` enum with `POUNDS`, `OUNCES`, `GRAMS`, and `KILOGRAMS`,
and use the existing `UnitOfMeasure` enum for `ItemQuantity.unitOfMeasure`.
This is a behavior-changing compatibility update and should include parsing
and request-serialization coverage.

### 6. Add missing Vendor Orders address fields

Amazon's `Address` model includes optional `county` and `district` fields.
The current model omits both, preventing typed consumers from accessing
values returned by the API.

Add optional string fields for `county` and `district` and test their response
deserialization.

## Implementation order

1. Add regression tests for report types, report options, marketplace IDs,
   report-document encoding, money precision, units, and address fields.
2. Apply the Reports compatibility changes, preserving public enum aliases
   where feasible.
3. Apply the Vendor Orders type corrections and missing fields.
4. Document compatibility notes for consumers that construct models directly.
5. Generate the library's model types from the official OpenAPI definitions,
   or add a repeatable comparison check, before future API releases.

## References

- [Amazon Reports API OpenAPI model](https://github.com/amzn/selling-partner-api-models/blob/main/models/reports-api-model/reports_2021-06-30.json)
- [Amazon Report Type Values](https://developer-docs.amazon.com/sp-api/docs/report-type-values)
- [Amazon Vendor Orders API OpenAPI model](https://github.com/amzn/selling-partner-api-models/blob/main/models/vendor-orders-api-model/vendorOrders.json)
- [Reports content-encoding change](https://github.com/amzn/selling-partner-api-models/commit/0b5887e428e629b85abe19961f88e5c8da7dee8a)
