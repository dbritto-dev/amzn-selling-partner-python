# codegen: the oagen Python emitter

[oagen](https://github.com/workos/oagen) is a framework for building SDK
generators, not a generator: it parses an OpenAPI spec into a typed IR and a
language emitter written in TypeScript turns that IR into files. There is no
built-in Python target; this directory is that emitter, plus the spec build
and resolution policy of this repository (laid out like
[workos/openapi-spec](https://github.com/workos/openapi-spec)).

```
spec/open-api-spec.yaml   the merged OpenAPI 3 document (committed; npm run spec:build writes it)
src/policy/               operation hints, mount rules, transforms (consumed by oagen.config.ts)
src/python/               the emitter: types.ts, models.ts, resources.ts, client.ts, index.ts
                          (+ naming.ts, pagination.ts, ratelimits.ts support modules)
src/spec/, src/convert.ts Amazon Swagger 2.0 files -> one OpenAPI 3 document
test/                     vitest (inline fixture spec, the tutorial's tasks-api.yml, helpers)
```

Generated SDK layout (`../src/amzn_selling_partner/sdk`, and `../tests/petstore_sdk`
for the test fixtures): `__init__.py`, `client.py` (`Client` / `AsyncClient`, one
resource per service, `with_options()`), `_http.py` (retry, backoff and timeout
constants from the IR's SDK behavior, token buckets, auth hook, pagination),
`errors.py` (from the error policy), `models/<package>/__init__.py` (all models
of an API version in one module, required fields first, `X | None = None`),
`models/<package>/enums.py` (`class X(str, Enum)` with `__str__ = str.__str__`),
`resources/<package>.py` (`<Service>Resource` / `Async<Service>Resource`, one
method per operation, `iter_<method>` for paginated ones).

## Commands

All from `codegen/`, after `npm ci --ignore-scripts` (Node 24; `--ignore-scripts`
skips the `tree-sitter-*` native builds oagen lists for its compat extractors,
which parse/resolve/generate never need).

| Command | What it does |
|---|---|
| `npm run spec:build` | Amazon models + notification schemas → `spec/open-api-spec.yaml` (`-- --petstore` → `spec/petstore.yaml`) |
| `npm run sdk:parse` | the full IR as JSON (`oagen parse`) |
| `npm run sdk:resolve -- --format table` | derived method name per operation (`oagen resolve`); collisions go to `src/policy/operation-hints.ts` |
| `npm run sdk:generate` | `oagen generate --lang python --spec spec/open-api-spec.yaml --namespace Client --output ../src/amzn_selling_partner/sdk`, into a clean output dir |
| `npm run generate` | spec build + the Amazon SDK + the petstore fixtures (`../tests/petstore_sdk`) |
| `npm run sdk:diff -- --old <previous.yaml>` | `oagen diff` of a previous spec against the committed one |
| `npm test` / `npm run typecheck` / `npm run build` | vitest, `tsc --noEmit`, tsup |

oagen formats every file it writes with ruff (import sorting, unused imports,
formatting) through the emitter's `formatCommand`: the enclosing project's
`.venv/bin/ruff`, or `ruff` on `PATH`. The generated SDK is tested by the
Python suite (`../tests/test_sdk_end_to_end.py` runs it over
`httpx2.MockTransport`: a list with an enum query parameter, a create with a
body model, a 404; `../tests/petstore_sdk` covers every operation shape).

Reproducing the tutorial on its own spec:

```sh
npx oagen parse --spec ../tests/fixtures/tasks-api.yml
npx oagen resolve --spec ../tests/fixtures/tasks-api.yml --format table
npx oagen generate --lang python --spec ../tests/fixtures/tasks-api.yml --namespace TasksClient --output ../tasks_sdk
```

No generated file is ever hand-edited: every fix lands in `src/python/` and is
re-verified by `npm run generate` (CI regenerates and fails on drift).

## oagen 0.30.2: what the tutorials get wrong, verified here

* **Registration.** Emitters register through the config object:
  `oagen.config.ts` spreads `plugin = { emitters: [pythonEmitter], extractors: [], smokeRunners: {} }`
  (`src/plugin.ts`). `registerEmitter()` exists but the CLI bundles its own
  registry copy and reports `Unknown language: python` when that is all you do.
* **`Emitter` interface.** `generateModels(models, ctx)`, `generateEnums(enums, ctx)`,
  `generateResources(services, ctx)`, `generateClient(spec, ctx)`,
  `generateErrors(ctx)` (ctx only), `generateTests(spec, ctx)`, `fileHeader()`.
  The `models` / `enums` arrays passed in are the scoped subset; this emitter
  reads `ctx.spec.models` / `ctx.spec.enums` so every package is complete.
* **`parseSpec(path, options?)`** takes a file path, not `{ content }`: the
  vitest inline fixture is written to a temp file first (`test/helpers.ts`).
* **`sdkBehavior`** is not a top-level `OagenConfig` key: the retry/timeout
  overrides live in `emitterOptions.python.sdkBehavior` and are merged over
  oagen's defaults with `mergeSdkBehavior(overrides)` (one argument); without
  them `ctx.spec.sdk` is used as is. The error policy (`ctx.spec.sdk.errors`)
  drives `errors.py`.
* **`ctx.resolvedOperations`** carries the hint-aware snake_case `methodName`;
  the resolver renames most Amazon operations (`getOrders` → `list_orders`)
  and derives colliding names for 29 of them (`src/policy/operation-hints.ts`).
  It also splits a service whose paths start with different segments
  (`/products/...` vs `/batches/...` of pricing v0): `mountRules`.
* **`op.pagination`** is never set for these specs (`ctx.spec.sdk.pagination`
  only carries `autoPageDelayMs`); `pagination.ts` detects the page token from
  the parameters and the response envelope, with an override table for the
  cases the heuristic cannot settle.
* **`op.requestBodyEncoding`** is `json` for every Amazon operation (uploads go
  to pre-signed S3 URLs outside the API); `form-data`, `form-urlencoded`,
  `binary` and `text` are still rendered (`files=` / `data=` / `content=`),
  covered by the inline fixture test.
* **Generating into an existing output directory merges** (`__init__.py`
  additively, the manifest prunes stale files): the `sdk:generate` script
  removes the output directory first and every `GeneratedFile` sets
  `overwriteExisting: true`.
* **Node.** oagen 0.30.2 declares `node >= 24.10.0`; the CLI shebang is
  `#!/usr/bin/env tsx` and the config is TypeScript, so run it through the npm
  scripts (they put `node_modules/.bin` on `PATH`).
* **Python 3.11+ `str()` on a `str` enum** returns `"TaskStatus.DONE"`; every
  generated enum sets `__str__ = str.__str__` and the HTTP layer encodes
  `Enum.value`, so `status=done` reaches the wire (asserted by the Python
  suite on the petstore and Amazon SDKs).

## What the reference leaves out and this emitter includes

Auto-pagination helpers (`iter_<method>`, driven by the detected page token),
an async client mirroring the sync one off a shared base, header parameters
and non-JSON bodies, `py.typed`. Per-operation `security` overrides and
`oagen diff` / compat overlays stay out: Amazon uses one LWA scheme, handled by
the plugin's auth hook.
