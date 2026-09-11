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

`codegen/` is laid out like an `oagen init --lang python` project: `src/python/`
is the emitter, `src/plugin.ts` the plugin bundle, `oagen.config.ts` the
consumer config (plugin + this repo's spec policy). oagen only parses OpenAPI 3
and its IR drops a few things the Amazon files rely on, so the driver
(`src/generate.ts`) does, per model file:

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
   parameters) come from the converted document (`extras.ts`).
5. `apis.py` and the package `__init__` files are written once from the
   registry; `ruff` formats everything.

`npm run sdk:generate` (alias `npm run generate`) runs all of it; `npm run
typecheck` and `npm test` check the generator itself. `npm ci --ignore-scripts`
skips the native builds of tree-sitter grammars oagen lists for its compat
extractors, which this project never loads.
