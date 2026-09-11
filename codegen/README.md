# codegen

The generator behind `src/amzn_selling_partner/{models,resources,apis.py}` and
`tests/petstore_sdk`. It is a small TypeScript project on top of
[oagen](https://github.com/workos/oagen) (`@workos/oagen`): oagen parses an
OpenAPI 3 document into its intermediate representation and calls the Python
emitter in `src/emitter/`, which returns the files to write.

```sh
npm ci --ignore-scripts      # oagen depends on tree-sitter grammars we never load; skip their native builds
npm run generate             # Amazon models + notification schemas + the petstore test package
npm run generate -- --only ordersV0 --no-format
npm run check                # tsc
npm test                     # emitter unit tests (node --test)
```

Pipeline per spec file (`src/generate.ts`):

1. `convert.ts` – Swagger 2.0 → OpenAPI 3.0 with `swagger2openapi`, after
   repairing the irregularities in the pinned files (`#ref` typos, dangling
   references).
2. `transform.ts` – pre-IR fixes oagen needs: inline alias schemas
   (`OrderList: array`), hoist inline objects into named components, and guard
   component names against oagen's singularising name cleaner.
3. `parseSpec` (oagen) with `operationIdTransform` = identity.
4. `emitter/` – models (pydantic v2 + `Literal` enums), resources (`Op`
   tables + sync/async classes), pagination detection and rate-limit parsing;
   `amazon.ts` holds the Amazon policy (file naming, aliases, pagination
   overrides). Facts the IR does not carry (body `required`, response media
   types, the `default` error response, greedy path parameters) are read from
   the converted document (`OperationExtras`).
5. `apis.py` and the package `__init__` files are written once from the
   registry; `ruff` formats everything.

`oagen.config.ts` registers the same emitter for the oagen CLI
(`npx oagen generate --spec .build/specs/<file>.json --lang python --output out`).
