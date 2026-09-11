import type { PaginationDescriptor } from './pagination.js';

/** Facts oagen's IR does not carry, recovered from the converted OpenAPI document by the driver. */
export interface OperationExtras {
  /** `requestBody.required` (oagen drops it). */
  bodyRequired?: boolean;
  /** 2xx status codes -> whether a schema is declared (oagen keeps only the primary response type). */
  successCodes?: Record<string, boolean>;
  /** 2xx status codes -> declared media types (oagen drops them; used for text/binary/SSE responses). */
  successMedia?: Record<string, string[]>;
  /** Path parameters flagged `x-amazon-spds-greedy-path-parameter` (slashes allowed). */
  greedyPathParams?: string[];
  /** Component name referenced by the `default` response (oagen drops non-numeric responses). */
  defaultErrorRef?: string;
  /** Operation summary (oagen keeps only the description). */
  summary?: string;
}

/** A component schema that is a bare oneOf/anyOf (oagen would emit an empty model). */
export interface UnionAlias {
  /** Referenced component names (after name cleaning) or inline type descriptions are not supported: refs only. */
  variants: string[];
  discriminator?: string;
  description?: string;
}

export interface EmitterOptions {
  /** Root schema of a wrapped JSON-Schema document; emitted as an empty model when oagen drops it. */
  rootSchema?: string;
  /** Union aliases keyed by component name (see `UnionAlias`). */
  unionAliases?: Record<string, UnionAlias>;
  /** Import root of the generated package, e.g. "amzn_selling_partner". */
  packageName: string;
  /** Package that provides `runtime/` (normally the same as packageName). */
  runtimePackage: string;
  api: string;
  version: string;
  /** Apply Amazon policy (rate-limit tables, pagination overrides). */
  amazon: boolean;
  /** Keyed by "METHOD /path". */
  extras: Record<string, OperationExtras>;
  /** Pagination override lookup (api, version, operationId). */
  paginationOverride?: (operationId: string) => PaginationDescriptor | undefined;
  /** Operations whose heuristic descriptor gets `drop_params_on_next=True`. */
  dropParamsOnNext?: (operationId: string) => boolean;
  /** Collects generation notes (unparsed rate limits, pagination decisions). */
  report?: GenerationReport;
}

export interface GenerationReport {
  unparsedRateLimits: string[];
  pagination: Record<string, string>;
  notes: string[];
}

export function newReport(): GenerationReport {
  return { unparsedRateLimits: [], pagination: {}, notes: [] };
}
