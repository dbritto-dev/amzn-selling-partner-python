import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseRateLimit } from '../src/python/ratelimits.js';

test('two-column and three-column usage plan tables', () => {
  const two = 'text\n\n**Usage Plan:**\n\n| Rate (requests per second) | Burst |\n| ---- | ---- |\n| 0.0167 | 20 |\n\nmore';
  const three = '| Plan type | Rate (requests per second) | Burst |\n| ---- | ---- | ---- |\n|Default| 5 | 10 |\n|Selling partner specific| Variable | Variable |\n';
  assert.deepEqual(parseRateLimit(two), { rate: 0.0167, burst: 20 });
  assert.deepEqual(parseRateLimit(three), { rate: 5, burst: 10 });
});

test('placeholder tables and missing tables are never guessed', () => {
  assert.equal(parseRateLimit('| Rate (requests per second) | Burst |\n| ---- | ---- |\n| n | n |\n'), null);
  assert.equal(parseRateLimit('no table'), null);
  assert.equal(parseRateLimit(undefined), null);
});
