import assert from 'node:assert/strict';
import { test } from 'vitest';
import { className, docstring, fieldName, methodName, paramName, snakeCase, Uniquer } from '../src/python/naming.js';

test('snake_case mirrors the runtime rules', () => {
  assert.equal(snakeCase('AmazonOrderId'), 'amazon_order_id');
  assert.equal(snakeCase('x-amzn-foo'), 'x_amzn_foo');
  assert.equal(snakeCase('getFeatureSKU'), 'get_feature_sku');
  assert.equal(snakeCase('IsISPU'), 'is_ispu');
});

test('reserved names get a trailing underscore', () => {
  assert.equal(fieldName('schema'), 'schema_');
  assert.equal(fieldName('model_config'), 'model_config_');
  assert.equal(fieldName('123abc'), 'n123abc');
  assert.equal(paramName('body'), 'body_');
  assert.equal(paramName('raw'), 'raw_');
  assert.equal(methodName('import'), 'import_');
  assert.equal(className('list'), 'List');
  assert.equal(className('Warning'), 'Warning_');
  assert.equal(className('buyBoxPrice'), 'BuyBoxPrice');
  assert.equal(className('Order'), 'Order');
});

test('docstrings escape triple quotes and backslashes', () => {
  assert.deepEqual(docstring('a """b""" c\\d', '    '), ['    """a \\"\\"\\"b\\"\\"\\" c\\\\d"""']);
  assert.deepEqual(docstring('line1\nline2', '  '), ['  """line1', '  line2', '  """']);
});

test('Uniquer suffixes duplicates', () => {
  const u = new Uniquer(['self']);
  assert.equal(u.take('self'), 'self_2');
  assert.equal(u.take('x'), 'x');
  assert.equal(u.take('x'), 'x_2');
});
