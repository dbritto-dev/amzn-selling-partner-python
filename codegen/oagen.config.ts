/**
 * oagen CLI configuration: the `python` target.
 *
 * The normal entry point is `npm run generate` (src/generate.ts), which runs
 * every pinned spec through the same emitter. This file lets the oagen CLI do
 * one spec at a time against the converted (OpenAPI 3) documents the driver
 * leaves in codegen/.build/converted; the output matches the driver's (before
 * ruff formatting):
 *
 *   OAGEN_API=orders OAGEN_VERSION=v0 npx oagen generate \
 *     --spec .build/converted/amzn_selling_partner__orders__v0.json --lang python --output out
 *   npx oagen resolve --spec .build/converted/amzn_selling_partner__orders__v0.json
 *   npx oagen diff --old <previous converted spec> --new .build/converted/<spec>.json
 *
 * OAGEN_API / OAGEN_VERSION name the API version (they decide module paths and
 * the Amazon pagination overrides); OAGEN_AMAZON=0 turns the Amazon policy off.
 */
import type { OagenConfig } from '@workos/oagen';
import { DROP_PARAMS_ON_NEXT, paginationOverride } from './src/amazon.js';
import type { JsonObject } from './src/convert.js';
import { pythonEmitter } from './src/emitter/index.js';
import { newReport, type EmitterOptions } from './src/emitter/options.js';
import { extractExtras, extractUnionAliases } from './src/extras.js';
import { schemaNameTransform, transformSpec } from './src/transform.js';

const api = process.env.OAGEN_API ?? 'api';
const version = process.env.OAGEN_VERSION ?? 'v1';
const amazon = process.env.OAGEN_AMAZON !== '0';

const options: EmitterOptions = {
  packageName: process.env.OAGEN_PACKAGE ?? 'amzn_selling_partner',
  runtimePackage: 'amzn_selling_partner',
  api,
  version,
  amazon,
  extras: {},
  report: newReport(),
  paginationOverride: amazon ? (opId) => paginationOverride(api, version, opId) : undefined,
  dropParamsOnNext: amazon ? (opId) => DROP_PARAMS_ON_NEXT.has(`${api}.${opId}`) : undefined,
};

const config: OagenConfig = {
  emitters: [pythonEmitter(options)],
  schemaNameTransform,
  operationIdTransform: (id) => id,
  transformSpec: (doc) => {
    const document = doc as unknown as JsonObject;
    // the pre-IR transform runs once, on the converted document: harvest what the IR drops first
    options.extras = extractExtras(document);
    options.unionAliases = extractUnionAliases(document);
    return transformSpec(document) as never;
  },
};

export default config;
