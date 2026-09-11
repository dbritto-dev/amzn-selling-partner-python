/**
 * oagen CLI configuration (the normal entry point is `npm run generate`, see
 * src/generate.ts; this file lets `npx oagen generate/resolve/diff` run against
 * one converted spec from codegen/.build/specs).
 */
import type { OagenConfig } from '@workos/oagen';
import { pythonEmitter } from './src/emitter/index.js';
import { schemaNameTransform, transformSpec } from './src/transform.js';
import { newReport } from './src/emitter/options.js';

const api = process.env.OAGEN_API ?? 'api';
const version = process.env.OAGEN_VERSION ?? 'v1';

const config: OagenConfig = {
  emitters: [
    pythonEmitter({
      packageName: process.env.OAGEN_PACKAGE ?? 'amzn_selling_partner',
      runtimePackage: 'amzn_selling_partner',
      api,
      version,
      amazon: process.env.OAGEN_AMAZON !== '0',
      extras: {},
      report: newReport(),
    }),
  ],
  schemaNameTransform,
  operationIdTransform: (id) => id,
  transformSpec: (doc) => transformSpec(doc as never) as never,
};

export default config;
