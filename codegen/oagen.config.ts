/**
 * oagen configuration: the `python` emitter plugin (`src/plugin.ts`) plus this
 * repository's resolution policy (`src/policy/`), as in workos/openapi-spec.
 *
 *   npm run spec:build     # Amazon Swagger 2.0 files -> spec/open-api-spec.yaml
 *   npm run sdk:resolve    # operation -> method name -> service table
 *   npm run sdk:generate   # oagen generate --lang python --spec spec/open-api-spec.yaml ...
 *   npm run regenerate     # both, plus the petstore fixtures and ruff
 */
import type { OagenConfig } from '@workos/oagen';
import { ALIASES } from './src/amazon.js';
import { plugin } from './src/plugin.js';
import { mountRules, operationHints, operationIdTransform, schemaNameTransform, transformSpec } from './src/policy/index.js';

const config: OagenConfig = {
  ...plugin,
  operationIdTransform,
  schemaNameTransform,
  operationHints,
  mountRules,
  emitterOptions: {
    python: {
      // SDK runtime policy, merged over oagen's defaults and generated into http_client.py.
      sdkBehavior: {
        retry: {
          retryableStatusCodes: [408, 429, 500, 502, 503, 504],
          maxRetries: 2,
          backoff: { initialDelay: 0.5, maxDelay: 8.0, multiplier: 2, jitterFactor: 0.5 },
        },
        timeout: { defaultTimeoutSeconds: 30, timeoutEnvVar: 'AMZN_SELLING_PARTNER_TIMEOUT' },
      },
      distribution: 'amzn_selling_partner',
      requestIdHeader: 'x-amzn-RequestId',
      rateHintHeader: 'x-amzn-RateLimit-Limit',
      // Path parameters that may contain `/` (the Uploads API `resource`).
      greedyPathParams: ['resource'],
      // `client.invoices` -> the `invoices_api_model` package, ...
      serviceAliases: ALIASES,
    },
  },
  transformSpec,
};
export default config;
