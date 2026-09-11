# Design notes

`amzn_selling_partner` is generated from the Amazon Selling Partner API models
(git submodule `spec/selling-partner-api-models`) by `codegen/`, an emitter
project built on [oagen](https://github.com/workos/oagen) the way the WorkOS
tutorial [How to build a custom SDK generator with oagen](https://workos.com/blog/build-a-custom-sdk-generator-with-oagen)
describes. This file records the decisions and what the generator had to work
around; the update procedure is in `UPDATING_SPECS.md`, the 0.1.x differences
in `../MIGRATION.md`.

## Decisions

1. Package and distribution names unchanged (`amzn-selling-partner` /
   `amzn_selling_partner`); Python 3.10+ (like the OpenAI SDK).
2. Runtime dependencies are `httpx2` and `pydantic>=2` only; `aiohttp` is an
   extra. Schemas, validation and parsing use pydantic v2.
3. The SDK is generated, standalone, at build time (decision of 2026-09-11,
   following the tutorial): `src/amzn_selling_partner/sdk/` holds everything
   the emitter produces from the spec (client, HTTP client, errors, models,
   resources) and is committed; CI regenerates it from the submodule and fails
   on drift; the wheel ships Python only.
4. Method names are oagen's resolved names (`list_orders`, `get_order`,
   `create_feed`), not Amazon's operationIds; the 29 operations whose derived
   names collide inside their API version are named through `operationHints`
   in `codegen/oagen.config.ts`. `sdk.resources.OPERATIONS` maps operationIds
   to methods, so the RDT / grantless tables, the sandbox runner and the 0.1.x
   wrappers stay keyed by Amazon's names.
5. One resource per API version (`client.orders_v0`, `client.orders` = newest),
   one models package per API version (`sdk.models.orders_v0`), notification
   payloads under `sdk.models.notifications.<schema file>`.
6. LWA-only auth (refresh-token and `client_credentials` grants, Restricted
   Data Tokens through the Tokens API); boto3 / SigV4 are gone. It is a plugin
   (`plugins/amazon_spapi.py`) over the generated `Auth` hook, not generated.
7. `date-time` → `datetime`, `date` → `date`, `byte`/`binary` → `bytes`, other
   formats stay `str`; enums are `str` (or `int`) `Enum` classes as in the
   tutorial; unknown fields are kept (`extra="allow"`); models are frozen.
8. Rate limits come from the usage-plan tables in the operation descriptions
   (never guessed) and are generated into each call as `RateLimit(rate, burst)`;
   pagination is detected from `nextToken`-style parameters with an override
   table for the operations the heuristic cannot settle, and generated as
   `iter_<method>` helpers; restricted (RDT) and grantless operations are
   hand-maintained tables in `plugins/_amazon/rdt.py` that still need checking
   against Amazon's Tokens API guide.

## The pipeline

```
spec/selling-partner-api-models        67 Swagger 2.0 files + 23 notification JSON Schemas (submodule)
        │  npm run spec:build           convert.ts (swagger2openapi, #ref/dangling-ref repairs), namespace components
        ▼                               as <package>:<Name>, tag every operation with its API version, merge
codegen/spec/open-api-spec.yaml        one OpenAPI 3 document (committed): 67 services, 373 operations, 2032 schemas
        │  oagen generate               oagen.config.ts = plugin + src/policy/: transformSpec (alias inlining,
        ▼                               inline-object hoisting, name protection), operationHints, mountRules
oagen IR (ApiSpec)                     services, operations, models, enums, sdk behavior
        │  src/python/ (the emitter)    types.ts, enums.ts, models.ts, resources.ts, client.ts, http_client.ts, errors.ts
        ▼
src/amzn_selling_partner/sdk/          client.py, http_client.py, errors.py, models/, resources/  (+ .oagen-manifest.json)
```

`npm run sdk:generate` runs the tutorial's command (`oagen generate --lang
python --spec spec/open-api-spec.yaml --namespace Client --output
../src/amzn_selling_partner/sdk`); `npm run regenerate` runs the whole thing
(spec build, Amazon into `sdk/`, the petstore fixtures into
`tests/petstore_sdk`, ruff). The layout follows
[workos/openapi-spec](https://github.com/workos/openapi-spec): the committed
spec in `spec/`, the resolution policy in `src/policy/` behind a thin
`oagen.config.ts`, `sdk:resolve` / `sdk:generate` / `sdk:diff` / `sdk:check`
scripts wrapping the `oagen` CLI.

### Step 0: the spec build (`src/spec/build.ts`)

oagen consumes one OpenAPI 3 document; Amazon ships 67 Swagger 2.0 files.
The build converts each file with `swagger2openapi` (after repairing the
`#ref` typo and the dangling references in the pinned models), renames its
components to `<package>:<Name>` (`orders_v0:Order`) so equally named schemas
of different API versions never collide, tags every operation with its API
version (`OrdersV0`: the oagen service, hence the resource class) and merges
everything. Notification JSON Schemas are wrapped into components under
`notifications.<file stem>:<Name>`; `x-root-schemas` remembers their roots.
Path collisions are an error (none in the pinned models).

### The policy (`src/policy/`, consumed by `oagen.config.ts`)

* `transformSpec` (`transforms.ts`): the pre-IR fixes oagen needs for these files. Named
  non-object schemas (`OrderList: array`, `MarketplaceId: string`, bare
  `oneOf` unions) would become empty models: they are inlined at every `$ref`
  site. Inline objects are hoisted to named components (`<Parent><Field>`).
  Every component name is replaced by an opaque token (`X17`) because oagen's
  `cleanSchemaName` singularises and re-cases names (`OrdersList` →
  `OrderList`, `ASINIdentifier` → `AsinIdentifier`); `schemaNameTransform`
  maps the token back.
* `operationIdTransform` (`transforms.ts`): identity (oagen would camelCase `getFeatureSKU`).
* `operationHints` (`operation-hints.ts`): the colliding derived names
  (`npm run sdk:resolve -- --format table` shows the table); the vitest suite
  fails on a hint that no longer names an operation of the committed spec.
* `mountRules` (`mount-rules.ts`): oagen splits a service whose paths start with different
  segments (`/products/...` and `/batches/...` of pricing v0); the rule mounts
  both back on `ProductPricingV0`.
* `emitterOptions.python` (in `oagen.config.ts`, language-specific like the
  example's `emitterOptions.node`): `sdkBehavior` (retry on 408/429/5xx, 2 retries,
  0.5 s initial delay, ×2, 8 s cap, 50 % jitter, 30 s timeout overridable with
  `AMZN_SELLING_PARTNER_TIMEOUT`), `requestIdHeader`, `rateHintHeader`,
  `greedyPathParams` (`resource` of the Uploads API), `serviceAliases`
  (`invoices` → `invoices_api_model`, ...), `distribution`.

### The emitter (`src/python/`)

* `types.ts` – `TypeRef` → Python type, an exhaustive switch with `assertNever`.
* `packages.ts` – where models and enums live: the `<package>:` prefix, or for
  unprefixed names (single-spec runs, enums oagen synthesises for inline
  parameter enums) the package of the service that uses them.
* `enums.ts` – `class Status(str, Enum)` per package (`models/<pkg>/enums.py`).
* `models.ts` – pydantic classes per package (`models/<pkg>/models.py`),
  required fields first, snake_case attributes with wire aliases, one file per
  package rather than per model so recursive references resolve inside one
  module; `models/_base.py` (`SpecModel`), package `__init__` re-exports.
* `resources.ts` – `resources/<pkg>.py`: `class OrdersV0Client` and
  `AsyncOrdersV0Client`, one method per resolved operation (from
  `ctx.resolvedOperations`) that builds `params`/`headers`/path explicitly and
  calls `self._client.request(...)` with the response model, the error model,
  the `RateLimit` and the operationId; `iter_<method>` for paginated
  operations; `resources/__init__.py` with the `SERVICES` / `OPERATIONS`
  registry.
* `client.ts` – `client.py`: the `--namespace` class (`Client` /
  `AsyncClient`) with one lazily created resource per service and a
  latest-version alias per API.
* `http_client.ts` – `http_client.py` from `ctx.spec.sdk`: retries, backoff,
  timeout, per-operation token buckets, the `Auth` hook, request encoding,
  response decoding, `paginate` / `apaginate`, the optional aiohttp transport.
* `errors.ts` – `errors.py` from the error policy (`BadRequestError`, ...,
  `RateLimitExceededError`, `ServerError`).

The emitter is registered in `src/plugin.ts` (`registerEmitter`) and
`oagen.config.ts` spreads the plugin, as in the tutorial. `npm run build`
(tsup), `npm run typecheck` and `npm test` (vitest over
`tests/fixtures/tasks-api.yml`, the tutorial's spec, and the helper modules)
work as in the scaffold. Two things the tutorial shows are not in the released
oagen (0.30.2): `sdkBehavior` as a top-level config key (here it is
`emitterOptions.python.sdkBehavior`, merged with `mergeSdkBehavior`) and
`parseSpec({ content })` (the tests parse the fixture file).

### Hand-written (never generated)

`plugins/amazon_spapi.py` (`SellingPartner(Client)` / `AsyncSellingPartner`:
regions, credentials, LWA auth hook with RDT and grantless scopes, document
helpers, notification registry), `plugins/_amazon/*`, the 0.1.x compatibility
subpackages (`client/`, `reports/`, `vendor/`, `utils/`), `sandbox_tests.py`,
`_examples.py`, `_naming.py`, `_compat.py`, `__init__.py`.

### Known irregularities in the pinned models

`B2bAnyOfferChangedNotification.json` spells a reference `#ref` (repaired),
`ShipmentTrackingMilestoneChangedNotification.json` is a dangling
`$ref` (becomes an empty model), `ListingsItemStatusChangeNotification.json`'s
own example contradicts its enum, `linkCarrierAccount` (Shipping v2) is the
operationId of two methods on one path (`OPERATIONS` keys the second one
`...:PUT`), 70 of the 2034 embedded sandbox examples violate their own schemas.

## Measured (Python 3.13, this container)

| | |
|---|---|
| import one resource (its models included) | 46 ms worst, 9 ms median |
| import all 67 resources | 742 ms |
| `import amzn_selling_partner` + `SellingPartner()` | 177 ms |
| generated method vs hand-written httpx2 call (`pytest benchmarks`, best of rounds) | 0.91 sync / 0.95 async |
| wheel | 551 KB, 347 Python files |
| pyright strict (hand-written + generated + tests/petstore_sdk) | 0 errors |
| tests | 116 pytest + 28 vitest; sandbox runner 1964 / 2034 examples |
