/** Language-specific settings: `emitterOptions.python` in oagen.config.ts, read from `ctx.emitterOptions`. */
import { mergeSdkBehavior, type DeepPartial, type EmitterContext, type SdkBehavior } from '@workos/oagen';

export interface EmitterOptions {
  /** Response header carrying the server's request id (surfaced on errors). */
  requestIdHeader: string;
  /** Response header carrying a rate hint after a 429 (requests per second); Amazon: `x-amzn-RateLimit-Limit`. */
  rateHintHeader?: string;
  /** Path parameters that may contain `/` (not percent-encoded). */
  greedyPathParams: string[];
  /** Python package name of the generated SDK, used in the User-Agent. */
  distribution: string;
  /** Extra client attributes: alias -> api or resource module (`invoices` -> `invoices_api_model`). */
  serviceAliases: Record<string, string>;
  /** Retry/timeout policy: oagen's defaults merged with `emitterOptions.python.sdkBehavior`. */
  sdk: SdkBehavior;
}

export function optionsOf(ctx: EmitterContext): EmitterOptions {
  const raw = (ctx.emitterOptions ?? {}) as Partial<Omit<EmitterOptions, 'sdk'>> & { sdkBehavior?: DeepPartial<SdkBehavior> };
  return {
    sdk: raw.sdkBehavior ? mergeSdkBehavior(raw.sdkBehavior) : ctx.spec.sdk,
    requestIdHeader: raw.requestIdHeader ?? 'x-request-id',
    rateHintHeader: raw.rateHintHeader,
    greedyPathParams: raw.greedyPathParams ?? [],
    distribution: raw.distribution ?? ctx.namespace,
    serviceAliases: raw.serviceAliases ?? {},
  };
}
