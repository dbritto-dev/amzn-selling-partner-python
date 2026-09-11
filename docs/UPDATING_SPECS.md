# Updating the bundled Amazon specs

The Amazon models are a git submodule at `spec/selling-partner-api-models`,
pinned to the commit recorded in `spec/PINNED_COMMIT`. During development the
package reads them straight from the submodule; a built wheel ships a copy
under `spapi/plugins/_amazon/{models,schemas}` made by
`python scripts/sync_specs.py` (the release workflow runs it before `uv build`;
the copies are git-ignored).

## 1. Bump the submodule

```sh
git -C spec/selling-partner-api-models fetch origin
git -C spec/selling-partner-api-models checkout <new commit or origin/main>
git -C spec/selling-partner-api-models rev-parse HEAD > spec/PINNED_COMMIT
```

## 2. Review what changed

```sh
python scripts/spec_naming.py --check       # every file maps to a unique api/version
python scripts/spec_naming.py               # the API/version table (paste into docs/PLAN.md §3 if it changed)
python scripts/spec_inventory.py            # operations, rate tables, sandbox examples, pagination, irregularities
```

Look at:

- **New API files or versions** – the naming rule (`spapi/plugins/_amazon/naming.py`)
  needs an entry in `_UNVERSIONED` only when a file stem carries no version
  suffix. Consider an alias in `ALIASES` for awkward names.
- **`latest`** moves automatically to the highest version.
- **Rate-limit tables** – `tests/test_amazon_plugin.py::test_rate_limit_counts_across_pinned_specs`
  pins the parsed/unparsed counts; update them after checking the new
  unparseable operations are genuinely table-less (never guess a limit).
- **Pagination** – run the pagination tests; new list operations that the
  heuristic leaves ambiguous need an entry in
  `spapi/plugins/_amazon/pagination.py` (`OVERRIDES`), and operations whose
  `nextToken` description says the other parameters must be omitted go in
  `DROP_PARAMS_ON_NEXT`.
- **Restricted / grantless operations** – compare the Tokens API use-case guide
  with `spapi/plugins/_amazon/rdt.py`; `test_restricted_and_grantless_tables_reference_real_operations`
  fails if an entry disappeared from the specs and `test_grantless_table_matches_descriptions`
  fails if a description mentions "grantless" for an unlisted operation.
- **Notification schemas** – `test_notification_models` validates every schema's
  own examples; the known-broken files are listed there.

## 3. Regenerate the stubs

```sh
python -m spapi.stubgen --out stubs
python -m spapi.stubgen --check   # what CI runs
```

Commit the `stubs/` changes together with the submodule bump.

## 4. Run everything

```sh
uv run pytest
uv run pyright
uv run python -m spapi.sandbox_tests           # all operations through both clients
uv run python scripts/report_load_times.py    # per-API build times (targets: < 50 ms cached, < 300 ms cold)
```

Then clear stale IR caches if you changed the loader (`IR_VERSION` in
`spapi/spec/cache.py` invalidates them for everyone).
