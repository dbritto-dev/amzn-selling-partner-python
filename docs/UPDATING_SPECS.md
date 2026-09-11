# Updating the bundled Amazon specs

The Amazon models are a git submodule at `spec/selling-partner-api-models`
(git records the pinned commit). They are an input of the generator only: the
package ships the Python that `codegen/` (an [oagen](https://github.com/workos/oagen)
emitter) generates from them, committed under `src/amzn_selling_partner/sdk`.

All commands run in `codegen/` after `npm ci --ignore-scripts` (Node 22;
`--ignore-scripts` skips the native builds of tree-sitter grammars oagen lists
for its compat extractors, which this project never loads).

## 1. Bump the submodule

```sh
git -C spec/selling-partner-api-models fetch origin
git -C spec/selling-partner-api-models checkout <new commit or origin/main>
```

## 2. Review what changed in the specs

Rebuild the merged OpenAPI 3 document (`spec/open-api-spec.yaml`, committed)
and diff it against the last committed version:

```sh
npm run spec:build      # -> spec/open-api-spec.yaml (+ .build/open-api-spec.report.json: services, warnings)
npm run sdk:diff        # oagen diff: last committed spec -> working tree (--old <ref|file> --new <file> to pick others)
```

`oagen diff` lists added/removed operations and parameter and schema changes.
(The build redacts the sample AWS access key IDs in Amazon's example URLs:
GitHub's push protection rejects a commit containing one.) Then check the method names oagen derives for the new operations:

```sh
npm run sdk:resolve -- --format table
```

Two operations of one API version that resolve to the same name need an entry
in `src/policy/operation-hints.ts` (the generator also reports them as
"collides" notes and suffixes the second one). A service that oagen splits
because its paths start with different segments (pricing v0) needs an entry in
`src/policy/mount-rules.ts`. `npm run sdk:parse` prints the IR when something
looks off; `npm run sdk:check` only loads the config and the spec.

## 3. Regenerate and review the generated code

```sh
npm run build          # the emitter (tsup), as in the tutorial
npm run sdk:generate   # oagen generate --lang python --spec spec/open-api-spec.yaml --namespace Client --output ../src/amzn_selling_partner/sdk
npm run regenerate     # or: spec build + sdk:generate + the petstore fixtures (spec/petstore.yaml -> tests/petstore_sdk) + ruff
git diff --stat -- spec ../src ../tests/petstore_sdk
```

Look at:

- **New API files or versions** – the naming rule lives in
  `codegen/src/amazon.ts` (`apiNaming`, `UNVERSIONED`, `ALIASES`) and is
  mirrored for the sandbox runner in
  `src/amzn_selling_partner/plugins/_amazon/specs.py`. A file whose stem
  carries no version suffix needs an `UNVERSIONED` entry in both. The
  latest-version alias (`client.orders`) moves automatically.
- **Rate-limit tables** – `test_rate_limit_counts_across_pinned_specs` pins the
  parsed/unparsed counts; `unparsed_rate_limits()` lists the operations without
  a table. Check they are genuinely table-less (never guess a limit) and update
  the counts.
- **Pagination** – `test_registry_matches_pinned_specs` pins the number of
  paginated operations (`OPERATIONS[...][3]`). New list operations that the
  heuristic leaves ambiguous need an entry in `codegen/src/amazon.ts`
  (`PAGINATION_OVERRIDES`); operations whose `nextToken` description says the
  other parameters must be omitted go in `DROP_PARAMS_ON_NEXT`.
- **Restricted / grantless operations** – compare the Tokens API use-case guide
  with `src/amzn_selling_partner/plugins/_amazon/rdt.py`;
  `test_restricted_and_grantless_tables_reference_real_operations` fails if an
  entry disappeared from the specs and `test_grantless_table_matches_descriptions`
  fails if a description mentions "grantless" for an unlisted operation.
- **Notification schemas** – `test_notification_models` validates every schema's
  own examples; the known-broken files are listed there.
- **Public API changes** – renamed operations or models show up in the diff of
  `src/amzn_selling_partner/sdk/resources` and `models`; `oagen diff` on the
  merged documents is the spec-level view.

## 4. Run everything

```sh
uv run ruff check src tests benchmarks && uv run ruff format --check src tests benchmarks
uv run pyright
uv run pytest
uvx nox -s security_test                              # bandit over the package (generated code included) + safety
uv run python -m amzn_selling_partner.sandbox_tests   # every operation against its embedded examples
```

bandit runs over the generated code too: the emitter marks the three kinds of
false positives it produces (`token_param="next_token"` in the `iter_` helpers,
enum members named like credentials, the jitter randomness in `_http.py`) with
targeted `# nosec` comments, so a real finding still fails the job.

Commit the submodule bump and the regenerated code together. CI regenerates
from the submodule and fails on any drift.

## The generator

`codegen/` is an oagen emitter project laid out like `oagen init --lang
python`, built the way the WorkOS tutorial
([How to build a custom SDK generator with oagen](https://workos.com/blog/build-a-custom-sdk-generator-with-oagen))
describes and organised like
[workos/openapi-spec](https://github.com/workos/openapi-spec): the spec in
`spec/`, the resolution policy in `src/policy/` (operation hints, mount rules,
transforms, consumed by a thin `oagen.config.ts`), the `sdk:*` scripts wrapping
the `oagen` CLI (`scripts/`), the emitter in `src/python/`. The tutorial's own
spec is checked in as `tests/fixtures/tasks-api.yml`, so every step can be
reproduced here:

1. **Inspect the IR.** `npm run sdk:parse -- --spec ../tests/fixtures/tasks-api.yml`
   prints oagen's intermediate representation, `npm run sdk:resolve -- --spec
   ../tests/fixtures/tasks-api.yml --format table` the resolution table
   (operation → method name → service).
2. **The emitter project.** `src/python/index.ts` assembles the `python`
   emitter from `types.ts` (IR `TypeRef` → Python annotation, exhaustive over
   every kind), `models.ts` (models + enums), `resources.ts` (one class per
   service, sync and async) and `client.ts` (root client, `__init__.py`,
   `errors.py`, `_http.py`); `src/plugin.ts` exports the plugin;
   `oagen.config.ts` spreads it and adds the policy barrel
   `src/policy/index.ts` (`transformSpec`, `schemaNameTransform`,
   `operationIdTransform`, `operationHints`, `mountRules`) plus
   `emitterOptions.python` with the `sdkBehavior` overrides that end up in
   `_http.py`.
3. **Generate.** `npm run build`, then `npm run sdk:generate -- --spec
   <spec.yml> --namespace <Client>` (`--output <dir>` for another
   destination) turns one spec into a standalone package (`__init__.py`,
   `client.py`, `_http.py`, `errors.py`, `models/`, `resources/`), starting
   from a clean output directory; without arguments
   it generates the Amazon SDK from `spec/open-api-spec.yaml`, which
   `npm run spec:build` writes from the Swagger 2.0 files (`--petstore` for
   the test fixtures, `spec/petstore.yaml`). `npm run regenerate` is the
   repository's full run: spec build, Amazon into
   `src/amzn_selling_partner/sdk`, the petstore fixtures into
   `tests/petstore_sdk`, then ruff.
4. **Test the emitter.** `npm test` (vitest: an inline fixture spec, written
   to a temp file because `parseSpec` takes a path, covering field ordering,
   nullable rendering and enum emission; the tutorial's `tasks-api.yml` for
   resources, client, HTTP layer and errors; the spec build and helper tests;
   the policy checked against the committed spec); `npm run typecheck`;
   `npm run build` (tsup); `npm run smoke` proves the output runs (the tasks
   SDK generated on the fly and the Amazon SDK over `httpx2.MockTransport`,
   printing the parsed results and the exact requests).
5. **Diff two spec versions.** `npm run sdk:diff` (last commit → working
   tree; `--old <ref or file> --new <file>` for any other pair).

Facts the emitter needs that oagen's IR does not carry are handled before the
IR (the spec build and `transformSpec`) or by configuration, never by reading
the raw document from the emitter: the emitter sees the IR only.
