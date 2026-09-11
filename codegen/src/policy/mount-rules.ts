/**
 * Service-level remounting. Maps IR service name → target service (PascalCase);
 * all operations of the source service are mounted on the target unless
 * overridden per operation in {@link operationHints}.
 *
 * The spec build tags every operation with its API version (`OrdersV0`), but
 * oagen also splits a service whose paths start with different first segments.
 * Product Pricing v0 is the one API whose paths do (`/products/pricing/v0/...`
 * and `/batches/products/pricing/v0/...`); both halves go back on one resource.
 * Keys may be exact service names or trailing-`*` prefix patterns.
 */
export const mountRules: Record<string, string> = {
  Products: 'ProductPricingV0',
  Batches: 'ProductPricingV0',
};
