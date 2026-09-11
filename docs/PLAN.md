# Design notes

`amzn_selling_partner` is generated from the Amazon Selling Partner API models
(git submodule `spec/selling-partner-api-models`) by `codegen/`, an emitter
project built on [oagen](https://github.com/workos/oagen). This file records
the decisions behind that and what the generator had to work around; the
update procedure is in `UPDATING_SPECS.md`, the 0.1.x differences in
`../MIGRATION.md`.

## Decisions

1. Package and distribution names unchanged (`amzn-selling-partner` /
   `amzn_selling_partner`); Python 3.10+ (like the OpenAI SDK).
2. Runtime dependencies are `httpx2` and `pydantic>=2` only; `aiohttp` is an
   extra. Schemas, validation and parsing use pydantic v2.
3. LWA-only auth (refresh-token and `client_credentials` grants, Restricted
   Data Tokens through the Tokens API); boto3 / SigV4 are gone.
4. One resource class per spec file (Amazon's tags are inconsistent), one models
   module per API version, `client.<api>.<version>` / `.latest` accessors.
5. The generated code is committed and CI regenerates it from the submodule and
   fails on drift; the wheel ships Python only.
6. `date-time` → `datetime`, `date` → `date`, `byte`/`binary` → `bytes`, other
   formats stay `str`; enums are `Literal` types; unknown fields are kept
   (`extra="allow"`); models are frozen.
7. Duplicate operationIds get the HTTP method appended
   (`link_carrier_account` / `link_carrier_account_post`); a class that would
   shadow a Python builtin gets a trailing underscore (`Warning_`).
8. Rate limits come from the usage-plan tables in the operation descriptions
   (never guessed); pagination is detected from `nextToken`-style parameters
   with an override table for the operations the heuristic cannot settle;
   restricted (RDT) and grantless operations are hand-maintained tables in
   `plugins/_amazon/rdt.py` that still need checking against Amazon's Tokens
   API guide.

## Design

Decision (user, 2026-09-11): generate the SDK at build time with
[oagen](https://github.com/workos/oagen) instead of loading specs at runtime.
The runtime (`runtime/`, auth, throttling, pagination, documents, compat) stays
hand-written; everything that used to be derived from the spec at import time
is now generated Python committed to the repository.

### What oagen does and does not give us (measured on the pinned models)

* All 67 model files are Swagger 2.0; oagen refuses them, so `codegen/` converts
  each one with `swagger2openapi` first (in memory, never committed).
* The IR loses named non-object schemas: `OrderList` (array), `MarketplaceId`
  (string) come out as models with no fields, `cleanSchemaName` singularises
  the leading word (`OrdersList` → `OrderList`, colliding with the real
  `OrderList`) and `toPascalCase` rewrites acronyms (`ASINIdentifier` →
  `AsinIdentifier`). The `transformSpec` hook fixes all of it before
  extraction: alias schemas are inlined at every `$ref` site, inline objects
  are hoisted to named components (`<Parent><Field>`), and every component
  name is replaced by an opaque token (`X17`) that survives cleaning;
  `schemaNameTransform` maps the token back to the original name.
* Field names keep the spec casing (`AmazonOrderId`), so the emitter can derive
  `amazon_order_id` + `Field(alias="AmazonOrderId")` exactly as before.
* oagen's pagination detector matches none of the 373 operations (it looks for
  `next_token`-style names on the query side and `data`-style envelopes on the
  response side). The emitter ports the heuristic from §9 and the Amazon
  override table; the result is emitted as a `Pagination(...)` literal.
* Rate-limit tables are parsed from operation descriptions at generation time
  and emitted as `RateLimit(rate, burst)` literals; operations without a
  parseable table are listed in `codegen/report.json`.
* Services follow tags, which are inconsistent across the Amazon files
  (`OrdersV0` + `Shipment`); the emitter flattens every service of a file into
  one resource class per API version, as before.
* `oagen extract`/`compat-*` ship a Python extractor, so future spec bumps can be
  checked with `oagen diff` (spec-level) and `oagen compat-diff` (API-surface
  level).

### Layout

```
codegen/                       the emitter project, laid out like `oagen init --lang python`
  package.json                 @workos/oagen 0.30.2, swagger2openapi; `sdk:generate`, `typecheck`, `test`
  oagen.config.ts              consumer config: the plugin bundle + this repo's spec policy (CLI use)
  src/plugin.ts, src/index.ts  plugin bundle / barrel
  src/python/                  the `python` emitter (models, resources, apis, naming, types, pagination, ratelimits)
  src/generate.ts              driver: every model file + notification schema through the emitter
  src/convert.ts               Swagger 2.0 → OpenAPI 3.0 (+ known-bad $ref fixes)
  src/transform.ts             alias inlining, inline-object hoisting, name protection
  src/extras.ts                facts the IR drops, read from the converted document
  src/amazon.ts                api naming, aliases, pagination overrides
  test/                        node --test unit tests for the emitter
src/amzn_selling_partner/
  models/<api>/<version>.py    pydantic v2 models, Literal enums (generated)
  models/notifications/*.py    notification payload models (generated)
  resources/<api>/<version>.py Op tables + Sync/Async resource classes (generated)
  apis.py                      API registry, typed accessors, aliases (generated)
  runtime/                     hand-written: base client, op/serializers, errors, pagination, throttle, auth, stream, transports
  plugins/                     hand-written: Amazon regions, LWA/RDT auth, documents, sandbox runner support
  client/, vendor/, reports/   compatibility package (unchanged API)
tests/petstore_sdk/            the same emitter run over tests/fixtures (proves the core is API-agnostic)
```

The wheel ships only Python; the spec submodule is a generator input. Enums
are always `Literal` types.

### Generated code shape

* Models: `class Order(SpecModel)` with snake_case attributes and wire aliases,
  `defer_build=True` so importing an API module costs class creation only.
* Resources: one module-level `Op(...)` literal per operation (URL template,
  parameter encoders, body kind, response/error model factories, rate limit,
  pagination), and one method per operation on `OrdersV0` / `AsyncOrdersV0` with
  an explicit keyword-only signature, so pyright and editors see the real types
  without stubs. Methods build a kwargs dict and call the runtime `_call`, the
  same hot path as before.
* `apis.py`: `class OrdersAPI` with `v0`, `v2026_01_01`, `latest`, `versions`
  and lazy imports; `class APIs` mixin with one typed attribute per API and the
  alias names; `Client`/`AsyncClient` mix it in.
* Amazon RDT/grantless tables stay in Python (`plugins/_amazon/rdt.py`) and are
  looked up by `(api, version, operationId)` from the auth hook.

### Regeneration and CI

```
cd codegen && npm ci --ignore-scripts && npm run generate   # writes src/amzn_selling_partner/{models,resources,apis.py} and tests/petstore_sdk
```

CI runs the generator on Node 22 and fails on `git diff --exit-code`, then the
Python matrix (ruff, pyright strict over hand-written and generated code,
pytest, smoke benchmark, wheel build). `docs/UPDATING_SPECS.md` describes the
submodule bump → `oagen diff` → regenerate → review flow. (`--ignore-scripts`:
oagen depends on tree-sitter grammars for its compat extractors; they are never
imported by the generator, so their native builds are skipped.)

### Measured (Python 3.12)

| | |
|---|---|
| import one API version | 50 ms worst, 10 ms median (class creation only) |
| import all 67 versions | 862 ms |
| `SellingPartner()` + warm every adapter | 12 ms after the imports |
| generated method vs hand-written httpx2 (`pytest benchmarks`, best of rounds) | 0.93 sync / 0.96 async |
| wheel | 3.0 MB of Python, no spec files |
| pyright strict | hand-written + generated code, 0 errors |

Every API version imports lazily on first attribute access, so a process that
touches two APIs pays for two modules; `preload()` imports everything.

Benchmarks are a [pytest-benchmark](https://pytest-benchmark.readthedocs.io/)
suite (`benchmarks/test_benchmarks.py`) over `httpx2.MockTransport`; CI runs
it on every push and asserts the 1.10x ratio; there is no nightly job.
