/**
 * Consumer config for the oagen CLI: the plugin bundle (the `python` target)
 * plus this repository's spec-interpretation policy.
 *
 * The normal entry point is `npm run sdk:generate` (src/generate.ts), which
 * runs every pinned spec through the same emitter. The CLI does one spec at a
 * time against the converted (OpenAPI 3) documents the driver leaves in
 * .build/converted and produces the same files (before ruff formatting):
 *
 *   OAGEN_API=orders OAGEN_VERSION=v0 npx oagen generate \
 *     --spec .build/converted/amzn_selling_partner__orders__v0.json --lang python --output out
 *   npx oagen resolve --spec .build/converted/amzn_selling_partner__orders__v0.json
 *   npx oagen diff --old <previous converted spec> --new .build/converted/<spec>.json
 *
 * OAGEN_API / OAGEN_VERSION name the API version (module paths, Amazon
 * pagination overrides); OAGEN_AMAZON=0 turns the Amazon policy off.
 */
import type { OagenConfig } from '@workos/oagen';
import { DROP_PARAMS_ON_NEXT, paginationOverride } from './src/amazon.js';
import type { JsonObject } from './src/convert.js';
import { extractExtras, extractUnionAliases } from './src/extras.js';
import { plugin } from './src/plugin.js';
import { configure, emitterOptions } from './src/python/index.js';
import { newReport } from './src/python/options.js';
import { schemaNameTransform, transformSpec } from './src/transform.js';

const api = process.env.OAGEN_API ?? 'api';
const version = process.env.OAGEN_VERSION ?? 'v1';
const amazon = process.env.OAGEN_AMAZON !== '0';

configure({
  packageName: process.env.OAGEN_PACKAGE ?? 'amzn_selling_partner',
  runtimePackage: 'amzn_selling_partner',
  api,
  version,
  amazon,
  extras: {},
  report: newReport(),
  paginationOverride: amazon ? (opId) => paginationOverride(api, version, opId) : undefined,
  dropParamsOnNext: amazon ? (opId) => DROP_PARAMS_ON_NEXT.has(`${api}.${opId}`) : undefined,
});

const config: OagenConfig = {
  ...plugin,
  schemaNameTransform,
  operationIdTransform: (id) => id,
  transformSpec: (doc) => {
    const document = doc as unknown as JsonObject;
    // the pre-IR transform runs once, on the converted document: harvest what the IR drops first
    emitterOptions.extras = extractExtras(document);
    emitterOptions.unionAliases = extractUnionAliases(document);
    return transformSpec(document) as never;
  },
};

export default config;
