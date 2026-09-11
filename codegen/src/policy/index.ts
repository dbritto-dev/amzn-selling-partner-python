/**
 * Resolution policy for the merged Selling Partner API spec
 * (`spec/open-api-spec.yaml`), laid out like workos/openapi-spec's
 * `src/policy/`: the single source of truth for what the generated SDK looks
 * like, independent of the emitter. `oagen.config.ts` consumes this barrel to
 * drive `oagen generate`; the vitest suite checks it against the committed
 * spec (every hint names an operation, every mount rule a service).
 */
export { operationHints } from './operation-hints.js';
export { mountRules } from './mount-rules.js';
export { operationIdTransform, schemaNameTransform, transformSpec } from './transforms.js';
