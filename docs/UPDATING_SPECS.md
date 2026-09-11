# Updating the bundled Amazon specs

The Amazon models are a git submodule at `spec/selling-partner-api-models`,
pinned to the commit recorded in `spec/PINNED_COMMIT`. They are an input of the
generator only: the package ships the Python that `codegen/` (built on
[oagen](https://github.com/workos/oagen)) generates from them, committed under
`src/amzn_selling_partner/{models,resources,apis.py}`.

## 1. Bump the submodule

```sh
git -C spec/selling-partner-api-models fetch origin
git -C spec/selling-partner-api-models checkout <new commit or origin/main>
git -C spec/selling-partner-api-models rev-parse HEAD > spec/PINNED_COMMIT
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

Commit the submodule bump, `spec/PINNED_COMMIT` and the regenerated code
together. CI regenerates from the submodule and fails on any drift.
