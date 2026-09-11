import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { ApiSpec, Model, Operation } from '@workos/oagen';
import { defaultSdkBehavior } from '@workos/oagen';
import { detectPagination } from '../src/emitter/pagination.js';
import { apiNaming, compareVersions, paginationOverride } from '../src/amazon.js';

const str = { kind: 'primitive', type: 'string' } as const;
function spec(models: Model[], op: Operation): ApiSpec {
  return { name: 't', version: '1', baseUrl: '', services: [{ name: 'S', operations: [op] }], models, enums: [], sdk: defaultSdkBehavior() };
}
function op(query: string[], response: string): Operation {
  return {
    name: 'list',
    httpMethod: 'get',
    path: '/x',
    pathParams: [],
    queryParams: query.map((name) => ({ name, type: str, required: false })),
    headerParams: [],
    response: { kind: 'model', name: response },
    errors: [],
    injectIdempotencyKey: false,
  };
}

test('token param + single array in the envelope', () => {
  const models: Model[] = [
    { name: 'Resp', fields: [{ name: 'payload', type: { kind: 'model', name: 'Payload' }, required: false }] },
    { name: 'Payload', fields: [{ name: 'Orders', type: { kind: 'array', items: { kind: 'model', name: 'Order' } }, required: true }, { name: 'NextToken', type: str, required: false }] },
    { name: 'Order', fields: [] },
  ];
  const d = detectPagination(spec(models, op(['NextToken'], 'Resp')), op(['NextToken'], 'Resp'), 'k');
  assert.deepEqual(d, { itemsPath: 'payload.Orders', nextTokenPath: 'payload.NextToken', nextTokenParam: 'NextToken', prevTokenPath: undefined, source: 'heuristic' });
});

test('two arrays are ambiguous; no token param means no pagination', () => {
  const models: Model[] = [
    { name: 'Resp', fields: [{ name: 'a', type: { kind: 'array', items: str }, required: false }, { name: 'b', type: { kind: 'array', items: str }, required: false }, { name: 'nextToken', type: str, required: false }] },
  ];
  const log: { key: string; message: string }[] = [];
  assert.equal(detectPagination(spec(models, op(['nextToken'], 'Resp')), op(['nextToken'], 'Resp'), 'k', log), null);
  assert.match(log[0]!.message, /2 array fields/);
  assert.equal(detectPagination(spec(models, op([], 'Resp')), op([], 'Resp'), 'k'), null);
});

test('amazon naming, versions and overrides', () => {
  assert.deepEqual(apiNaming('orders_2021-08-01'), ['orders', 'v2021_08_01']);
  assert.deepEqual(apiNaming('ordersV0'), ['orders', 'v0']);
  assert.deepEqual(apiNaming('vendorOrders', '1.0'), ['vendor_orders', 'v1']);
  assert.deepEqual(apiNaming('unknownFile', '2.5'), ['unknown_file', 'v2_5']);
  assert.deepEqual(['v2026_01_01', 'v0', 'v2', 'v2021_08_01'].sort(compareVersions), ['v0', 'v2', 'v2021_08_01', 'v2026_01_01']);
  assert.equal(paginationOverride('orders', 'v0', 'getOrders')?.dropParamsOnNext, true);
  assert.equal(paginationOverride('reports', 'v2021_06_30', 'getReports')?.itemsPath, 'reports');
  assert.equal(paginationOverride('orders', 'v0', 'getOrder'), undefined);
});
