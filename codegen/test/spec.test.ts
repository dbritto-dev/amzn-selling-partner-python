import { describe, expect, it } from 'vitest';
import { mergeDocuments, namespaceComponents, serviceName } from '../src/spec/build.js';

const doc = (title: string) => ({
  openapi: '3.0.3',
  info: { title, version: '1' },
  paths: { '/things': { get: { operationId: 'listThings', tags: ['Things'], responses: { '200': { description: 'ok', content: { 'application/json': { schema: { $ref: '#/components/schemas/Thing' } } } } } } } },
  components: { schemas: { Thing: { type: 'object', properties: { id: { type: 'string' } } } }, parameters: { P: { name: 'p', in: 'query', schema: { type: 'string' } } } },
});

describe('spec build', () => {
  it('names services after the API version', () => {
    expect(serviceName('orders', 'v0')).toBe('OrdersV0');
    expect(serviceName('fba_inbound', 'v2024_03_20')).toBe('FbaInboundV20240320');
  });

  it('namespaces components and rewrites references', () => {
    const out = namespaceComponents(doc('A'), 'a_v1') as typeof doc extends (t: string) => infer R ? R : never;
    expect(Object.keys(out.components.schemas)).toEqual(['a_v1:Thing']);
    expect(Object.keys(out.components.parameters)).toEqual(['a_v1:P']);
    expect(out.paths['/things'].get.responses['200'].content['application/json'].schema.$ref).toBe('#/components/schemas/a_v1:Thing');
  });

  it('merges documents, tags every operation with its service and rejects path collisions', () => {
    const merged = mergeDocuments(
      [
        { document: doc('A'), pkg: 'a_v1', service: 'AV1', pathPrefix: '/a' },
        { document: { ...doc('B'), 'x-root-schema': 'Thing' }, pkg: 'b_v1', service: 'BV1', pathPrefix: '/b' },
      ],
      { title: 'Merged', version: '1' },
      [{ url: 'https://example.com' }],
    ) as Record<string, any>;
    expect(Object.keys(merged.paths)).toEqual(['/a/things', '/b/things']);
    expect(merged.paths['/a/things'].get.tags).toEqual(['AV1']);
    expect(merged.tags).toEqual([{ name: 'AV1' }, { name: 'BV1' }]);
    expect(Object.keys(merged.components.schemas)).toEqual(['a_v1:Thing', 'b_v1:Thing']);
    expect(merged['x-root-schemas']).toEqual(['b_v1:Thing']);
    expect(() => mergeDocuments([{ document: doc('A'), pkg: 'a', service: 'A' }, { document: doc('B'), pkg: 'b', service: 'B' }], { title: 'x', version: '1' }, [])).toThrow(/defined by both/);
  });
});
