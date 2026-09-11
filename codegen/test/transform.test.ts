import assert from 'node:assert/strict';
import { test } from 'vitest';
import { isAliasSchema, liftInlineObjects, NAME_GUARD, schemaNameTransform, transformSpec } from '../src/transform.js';

const doc = {
  openapi: '3.0.3',
  info: { title: 't', version: '1' },
  paths: {
    '/orders': {
      get: {
        operationId: 'getOrders',
        responses: { '200': { description: 'ok', content: { 'application/json': { schema: { $ref: '#/components/schemas/OrdersList' } } } } },
      },
    },
  },
  components: {
    schemas: {
      OrdersList: {
        type: 'object',
        properties: {
          Orders: { $ref: '#/components/schemas/OrderList', description: 'the orders' },
          Meta: { type: 'object', properties: { Count: { type: 'integer' } } },
          Attributes: { $ref: '#/components/schemas/AttributeMap' },
        },
      },
      OrderList: { type: 'array', items: { $ref: '#/components/schemas/Order' } },
      AttributeMap: { type: 'object', additionalProperties: { type: 'string' } },
      Order: { type: 'object', properties: { Id: { $ref: '#/components/schemas/MarketplaceId' } } },
      MarketplaceId: { type: 'string', description: 'id' },
      Animal: { oneOf: [{ $ref: '#/components/schemas/Order' }], discriminator: { propertyName: 'k', mapping: { o: '#/components/schemas/Order' } } },
    },
  },
};

test('alias schemas are inlined and every remaining component is guarded', () => {
  const out = transformSpec(structuredClone(doc)) as typeof doc;
  const raw = out.components.schemas as Record<string, Record<string, unknown>>;
  const schemas: Record<string, Record<string, unknown>> = {};
  for (const [k, v] of Object.entries(raw)) schemas[schemaNameTransform(k)] = v;
  const ref = (r: string): string => schemaNameTransform(r.slice('#/components/schemas/'.length));
  assert.ok(Object.keys(raw).every((k) => new RegExp(`^${NAME_GUARD}\\d+$`).test(k)));
  assert.deepEqual(Object.keys(schemas).sort(), ['Animal', 'Order', 'OrdersList', 'OrdersListMeta']);
  const orders = (schemas.OrdersList!.properties as Record<string, Record<string, unknown>>).Orders!;
  assert.equal(orders.type, 'array');
  assert.equal(ref((orders.items as Record<string, string>).$ref!), 'Order');
  assert.equal(orders.description, 'the orders');
  const attrs = (schemas.OrdersList!.properties as Record<string, Record<string, unknown>>).Attributes!;
  assert.deepEqual(attrs, { type: 'object', additionalProperties: { type: 'string' } });
  assert.deepEqual((schemas.Order!.properties as Record<string, unknown>).Id, { type: 'string', description: 'id' });
  const disc = schemas.Animal!.discriminator as { mapping: Record<string, string> };
  assert.equal(ref(disc.mapping.o!), 'Order');
  const resp = (out.paths['/orders'].get.responses['200'].content['application/json'].schema as Record<string, string>).$ref!;
  assert.equal(ref(resp), 'OrdersList');
  assert.equal(schemaNameTransform('Unknown'), 'Unknown');
});

test('inline objects are hoisted to named components', () => {
  const lifted = liftInlineObjects({ A: { type: 'object', properties: { b: { type: 'object', properties: { c: { type: 'array', items: { type: 'object', properties: { d: { type: 'string' } } } } } } } } });
  assert.deepEqual(Object.keys(lifted).sort(), ['A', 'AB', 'ABCItem']);
  assert.deepEqual((lifted.A as { properties: Record<string, unknown> }).properties.b, { $ref: '#/components/schemas/AB' });
});

test('a stray properties object next to type: array is not an object', () => {
  const lifted = liftInlineObjects({ A: { type: 'object', properties: { list: { type: 'array', properties: { junk: { type: 'object', properties: { x: {} } } }, items: { type: 'object', properties: { y: { type: 'string' } } } } } } });
  assert.deepEqual(Object.keys(lifted).sort(), ['A', 'AListItem']);
});

test('isAliasSchema', () => {
  assert.equal(isAliasSchema({ type: 'string', enum: ['a'] }), false);
  assert.equal(isAliasSchema({ type: 'object', properties: { a: {} } }), false);
  assert.equal(isAliasSchema({ type: 'object' }), true);
  assert.equal(isAliasSchema({ type: 'array', items: {} }), true);
});
