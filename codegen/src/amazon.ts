/**
 * Amazon-specific generation policy: API attribute names for the model files
 * (docs/PLAN.md §3), aliases, and the pagination overrides the heuristic cannot
 * settle (§9). Restricted-operation and grantless tables stay in Python
 * (`plugins/_amazon/rdt.py`) because the auth hook reads them at run time.
 */
import type { PaginationDescriptor } from './emitter/pagination.js';
import { snakeCase } from './emitter/naming.js';

const VERSION_SUFFIX = /(?:[_-]|(?<=[a-z])V)(?<v>\d{4}-\d{2}-\d{2}|\d+)$/;

/** stem -> version for files whose stem carries no version (from info.version). */
export const UNVERSIONED: Record<string, string> = {
  fbaInbound: 'v1',
  fbaInventory: 'v1',
  messaging: 'v1',
  notifications: 'v1',
  sales: 'v1',
  sellers: 'v1',
  services: 'v1',
  shipping: 'v1',
  solicitations: 'v1',
  vendorInvoices: 'v1',
  vendorOrders: 'v1',
  vendorShipments: 'v1',
  vendorTransactionStatus: 'v1',
};

/** Friendlier attribute names on top of the mechanical ones (alias -> canonical). */
export const ALIASES: Record<string, string> = {
  invoices: 'invoices_api_model',
  product_type_definitions: 'definitions_product_types',
  fba_inbound_eligibility: 'fba_inbound',
  amazon_warehousing_and_distribution: 'awd',
  application_integrations: 'app_integrations',
};

export function normalizeVersion(raw: string): string {
  const v = raw.trim().replace(/^[vV]/, '').replace(/[^0-9a-zA-Z_]+/g, '_').replace(/^_+|_+$/g, '');
  return 'v' + (v || '0');
}

/** `orders_2021-08-01.json` -> `["orders", "v2021_08_01"]`; `ordersV0` -> `["orders", "v0"]`. */
export function apiNaming(stem: string, infoVersion?: string): [string, string] {
  const m = VERSION_SUFFIX.exec(stem);
  if (m && m.groups) return [snakeCase(stem.slice(0, m.index)), 'v' + m.groups.v!.replace(/-/g, '_')];
  const fixed = UNVERSIONED[stem];
  if (fixed) return [snakeCase(stem), fixed];
  return [snakeCase(stem), normalizeVersion(infoVersion ?? '0')];
}

export function versionKey(v: string): [number, string] {
  const body = v.startsWith('v') ? v.slice(1) : v;
  return body.includes('_') ? [1, body] : [0, body.padStart(6, '0')];
}

export function compareVersions(a: string, b: string): number {
  const [ka, sa] = versionKey(a);
  const [kb, sb] = versionKey(b);
  if (ka !== kb) return ka - kb;
  return sa < sb ? -1 : sa > sb ? 1 : 0;
}

type Key = `${string}.${string}.${string}`; // api.version|*.operationId

function d(p: Omit<PaginationDescriptor, 'source'>): PaginationDescriptor {
  return { ...p, source: 'override' };
}

/** (api, version or "*", operationId) -> descriptor. */
export const PAGINATION_OVERRIDES: Record<Key, PaginationDescriptor> = {
  'orders.v0.getOrders': d({ itemsPath: 'payload.Orders', nextTokenPath: 'payload.NextToken', nextTokenParam: 'NextToken', dropParamsOnNext: true }),
  'orders.v0.getOrderItems': d({ itemsPath: 'payload.OrderItems', nextTokenPath: 'payload.NextToken', nextTokenParam: 'NextToken', dropParamsOnNext: true }),
  'orders.v0.getOrderItemsBuyerInfo': d({ itemsPath: 'payload.OrderItems', nextTokenPath: 'payload.NextToken', nextTokenParam: 'NextToken', dropParamsOnNext: true }),
  'reports.*.getReports': d({ itemsPath: 'reports', nextTokenPath: 'nextToken', nextTokenParam: 'nextToken', dropParamsOnNext: true }),
  'feeds.*.getFeeds': d({ itemsPath: 'feeds', nextTokenPath: 'nextToken', nextTokenParam: 'nextToken', dropParamsOnNext: true }),
  'catalog_items.v2020_12_01.searchCatalogItems': d({ itemsPath: 'items', nextTokenPath: 'pagination.nextToken', nextTokenParam: 'pageToken', prevTokenPath: 'pagination.previousToken' }),
  'catalog_items.v2022_04_01.searchCatalogItems': d({ itemsPath: 'items', nextTokenPath: 'pagination.nextToken', nextTokenParam: 'pageToken', prevTokenPath: 'pagination.previousToken' }),
  'listings_items.v2021_08_01.searchListingsItems': d({ itemsPath: 'items', nextTokenPath: 'pagination.nextToken', nextTokenParam: 'pageToken', prevTokenPath: 'pagination.previousToken' }),
  'data_kiosk.*.getQueries': d({ itemsPath: 'queries', nextTokenPath: 'pagination.nextToken', nextTokenParam: 'paginationToken', dropParamsOnNext: true }),
  'fba_inventory.*.getInventorySummaries': d({ itemsPath: 'payload.inventorySummaries', nextTokenPath: 'pagination.nextToken', nextTokenParam: 'nextToken', dropParamsOnNext: true }),
  'notifications.*.getSubscriptions': d({ itemsPath: 'payload.subscriptions', nextTokenPath: 'payload.nextToken', nextTokenParam: 'nextToken', dropParamsOnNext: true }),
  'aplus_content.*.searchContentDocuments': d({ itemsPath: 'contentMetadataRecords', nextTokenPath: 'nextPageToken', nextTokenParam: 'pageToken' }),
  'aplus_content.*.listContentDocumentAsinRelations': d({ itemsPath: 'asinMetadataSet', nextTokenPath: 'nextPageToken', nextTokenParam: 'pageToken' }),
  'aplus_content.*.searchContentPublishRecords': d({ itemsPath: 'publishRecordList', nextTokenPath: 'nextPageToken', nextTokenParam: 'pageToken' }),
  'services.*.getServiceJobs': d({ itemsPath: 'payload.jobs', nextTokenPath: 'payload.nextPageToken', nextTokenParam: 'pageToken', prevTokenPath: 'payload.previousPageToken' }),
  'fulfillment_inbound.v2024_03_20.getSelfShipAppointmentSlots': d({ itemsPath: 'selfShipAppointmentSlotsAvailability.slots', nextTokenPath: 'pagination.nextToken', nextTokenParam: 'paginationToken' }),
  'promotions.*.getSelection': d({ itemsPath: 'selection.selectionDetails.items', nextTokenPath: 'selection.selectionDetails.pagination.nextToken', nextTokenParam: 'paginationToken' }),
  'finances.v0.listFinancialEventGroups': d({ itemsPath: 'payload.FinancialEventGroupList', nextTokenPath: 'payload.NextToken', nextTokenParam: 'NextToken', dropParamsOnNext: true }),
  'finances.v0.listFinancialEventsByGroupId': d({ itemsPath: 'payload.FinancialEvents', nextTokenPath: 'payload.NextToken', nextTokenParam: 'NextToken', itemsIsObject: true, dropParamsOnNext: true }),
  'finances.v0.listFinancialEventsByOrderId': d({ itemsPath: 'payload.FinancialEvents', nextTokenPath: 'payload.NextToken', nextTokenParam: 'NextToken', itemsIsObject: true, dropParamsOnNext: true }),
  'finances.v0.listFinancialEvents': d({ itemsPath: 'payload.FinancialEvents', nextTokenPath: 'payload.NextToken', nextTokenParam: 'NextToken', itemsIsObject: true, dropParamsOnNext: true }),
};

/** Operations whose `nextToken` description says the other parameters must be omitted. */
export const DROP_PARAMS_ON_NEXT = new Set<string>([
  'orders.getOrders',
  'orders.getOrderItems',
  'orders.getOrderItemsBuyerInfo',
  'reports.getReports',
  'feeds.getFeeds',
  'data_kiosk.getQueries',
  'fba_inventory.getInventorySummaries',
  'notifications.getSubscriptions',
  'finances.listFinancialEventGroups',
  'finances.listFinancialEventsByGroupId',
  'finances.listFinancialEventsByOrderId',
  'finances.listFinancialEvents',
]);

export function paginationOverride(api: string, version: string, operationId: string): PaginationDescriptor | undefined {
  return PAGINATION_OVERRIDES[`${api}.${version}.${operationId}`] ?? PAGINATION_OVERRIDES[`${api}.*.${operationId}`];
}
