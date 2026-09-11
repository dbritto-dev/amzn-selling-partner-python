# Updating the bundled Amazon specs

The Amazon models are a git submodule at `spec/selling-partner-api-models`
(git records the pinned commit). They are an input of the generator only: the package ships the Python that `codegen/` (built on
[oagen](https://github.com/workos/oagen)) generates from them, committed under
`src/amzn_selling_partner/{models,resources,apis.py}`.

## 1. Bump the submodule

```sh
git -C spec/selling-partner-api-models fetch origin
git -C spec/selling-partner-api-models checkout <new commit or origin/main>
```

## 2. Review what changed in the specs

`oagen diff` classifies the changes of one API as additive, modified or
breaking (Swagger 2.0 files must be converted first; the generator leaves the
converted documents under `codegen/.build/converted`):

```sh
cd codegen
npm ci --ignore-scripts
npm run generate                                   # also refreshes codegen/.build/converted/*.json
git stash -- ../src ../tests/petstore_sdk          # keep the previous generation for the diff, if you want it
npx oagen diff --old <previous converted spec> --new .build/converted/amzn_selling_partner__orders__v0.json
```

`codegen/.build/report.json` lists, for the whole run, the spec repairs that were
needed (`#ref` typos, dangling references), the operations without a parseable
rate-limit table, every pagination decision and the notes (duplicate
operationIds, cookie parameters, ...).

## 3. Regenerate and review the generated code

```sh
cd codegen && npm run generate
git diff --stat -- src tests/petstore_sdk
```

Look at:

- **New API files or versions** – the naming rule lives in
  `codegen/src/amazon.ts` (`apiNaming`, `UNVERSIONED`, `ALIASES`) and is
  mirrored for the sandbox runner in
  `src/amzn_selling_partner/plugins/_amazon/specs.py`. A file whose stem
  carries no version suffix needs an `UNVERSIONED` entry in both.
- **`latest`** moves automatically to the highest version (`apis.py`).
- **Rate-limit tables** – `test_rate_limit_counts_across_pinned_specs` pins the
  parsed/unparsed counts; check the new unparseable operations in
  `codegen/.build/report.json` are genuinely table-less (never guess a limit)
  and update the counts.
- **Pagination** – `test_pagination_annotations` pins the number of paginated
  operations. New list operations that the heuristic leaves ambiguous need an
  entry in `codegen/src/amazon.ts` (`PAGINATION_OVERRIDES`); operations whose
  `nextToken` description says the other parameters must be omitted go in
  `DROP_PARAMS_ON_NEXT` (`test_drop_params_descriptions_match_generated_descriptors`
  checks the generated descriptors against that list).
- **Restricted / grantless operations** – compare the Tokens API use-case guide
  with `src/amzn_selling_partner/plugins/_amazon/rdt.py`;
  `test_restricted_and_grantless_tables_reference_real_operations` fails if an
  entry disappeared from the specs and `test_grantless_table_matches_descriptions`
  fails if a description mentions "grantless" for an unlisted operation.
- **Notification schemas** – `test_notification_models` validates every schema's
  own examples; the known-broken files are listed there.
- **Public API changes** – renamed operations or models show up in the diff of
  `src/amzn_selling_partner/resources` and `models`; `oagen compat-extract`
  (`--lang python`) can snapshot the public surface before and after a bump.

## 4. Run everything

```sh
uv run ruff check src tests benchmarks && uv run ruff format --check src tests benchmarks
uv run pyright
uv run pytest
uv run python -m amzn_selling_partner.sandbox_tests   # every operation against its embedded examples
```

Commit the submodule bump and the regenerated code together. CI regenerates
from the submodule and fails on any drift.

## The generator

`codegen/` is an oagen emitter project built the way the WorkOS tutorial
([How to build a custom SDK generator with oagen](https://workos.com/blog/build-a-custom-sdk-generator-with-oagen))
describes; the tutorial's own spec is checked in as `tests/fixtures/tasks-api.yml`
so every step can be reproduced here. All commands run in `codegen/` after
`npm ci --ignore-scripts` (Node 22; `--ignore-scripts` skips the native builds
of tree-sitter grammars oagen lists for its compat extractors, which this
project never loads).

1. **Look at the IR before touching the emitter.** `npm run sdk:parse -- --spec
   ../tests/fixtures/tasks-api.yml` prints oagen's intermediate representation
   (services, operations, models, enums); `npm run sdk:resolve -- --spec
   ../tests/fixtures/tasks-api.yml --format table` prints the resolution table
   (operation → method name → service). The Amazon files are Swagger 2.0, so
   convert them first: `npm run sdk:generate -- --only orders` leaves the
   OpenAPI 3 documents in `.build/converted/`, then
   `npm run sdk:parse -- --spec .build/converted/amzn_selling_partner__orders__v0.json`.
2. **The emitter project** is what `oagen init --lang python` scaffolds:
   `src/python/index.ts` assembles the `python` emitter from `types.ts` (IR
   `TypeRef` → Python type, exhaustive over every kind), `enums.ts`,
   `models.ts`, `resources.ts` and `client.ts`; `src/plugin.ts` registers it;
   `oagen.config.ts` spreads the plugin and adds this repository's spec policy
   (`transformSpec`, `schemaNameTransform`, `operationIdTransform`,
   `emitterOptions.python`); `vitest.config.ts` and `test/` hold the tests.
3. **Generate.** `npm run sdk:generate -- --spec <spec> --namespace <Client>`
   turns one spec (OpenAPI 3 or Swagger 2.0, JSON or YAML) into a standalone
   package under `codegen/sdk/` (`--output` to change it; `--api`/`--version`
   to name the module, `--amazon` to apply the Amazon policy):

   ```
   npm run sdk:generate -- --spec ../tests/fixtures/tasks-api.yml --namespace TasksClient --api tasks --version v1
   PYTHONPATH=.. python -c "from sdk.client import TasksClient; print(TasksClient(base_url='https://api.tasks.example.com').tasks.v1.list_tasks)"
   ```

   `npm run sdk:generate` with no `--spec` is the repository's driver: every
   pinned model file and notification schema → `src/amzn_selling_partner/{models,resources,apis.py}`,
   and the petstore fixtures → `tests/petstore_sdk`. `npm run sdk:generate:python --
   --spec <openapi3.json> --output <dir>` runs the oagen CLI itself
   (`OAGEN_API`/`OAGEN_VERSION` name the module; `OAGEN_AMAZON=0` turns the
   Amazon policy off) and produces the same files as the driver.
4. **Test the emitter.** `npm test` (vitest) runs the fixture-spec tests
   (`test/models.test.ts`, `test/resources.test.ts`, `test/client.test.ts`
   over `tasks-api.yml`) and the unit tests of the helpers; `npm run typecheck`
   type-checks the generator.
5. **Diff two spec versions.** `npm run sdk:diff -- --old <previous> --new
   <current>` reports added/removed operations and parameter/schema changes
   (see "Review what changed in the specs" above).

What the driver does per model file, because oagen only parses OpenAPI 3 and
its IR drops a few things the Amazon files rely on:

1. `convert.ts` – Swagger 2.0 → OpenAPI 3.0 with `swagger2openapi`, after
   repairing the `#ref` typo and the dangling references in the pinned files.
2. `transform.ts` – pre-IR fixes: inline alias schemas (`OrderList: array`),
   hoist inline objects into named components, replace component names by
   opaque tokens so oagen's name cleaner cannot rewrite them (`ASINIdentifier`
   would become `AsinIdentifier`); `schemaNameTransform` maps them back.
3. `parseSpec` (oagen) with `operationIdTransform` = identity.
4. the `python` emitter: models (pydantic v2, `Literal` enums), resources (`Op`
   tables + sync/async classes), pagination detection, rate-limit parsing;
   `amazon.ts` holds the Amazon policy. Facts the IR does not carry (body
   `required`, response media types, the `default` error response, greedy path
   parameters) come from the converted document (`extras.ts`). Per-spec
   settings (package, API, version, Amazon policy, those extras) reach the
   emitter through oagen's `emitterOptions` bag: the driver passes it to
   `generateFiles`, `oagen.config.ts` declares it as `emitterOptions.python`.
5. `apis.py`, `client.py` and the package `__init__` files are written once
   from the registry (`client.ts`); `ruff` formats everything.
