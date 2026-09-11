import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import YAML from 'yaml';
import { describe, expect, it } from 'vitest';
import { mountRules, operationHints, operationIdTransform } from '../src/policy/index.js';

const SPEC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'spec', 'open-api-spec.yaml');
const METHODS = ['get', 'put', 'post', 'delete', 'options', 'head', 'patch', 'trace'];

interface Doc {
  paths: Record<string, Record<string, { tags?: string[] }>>;
  tags: { name: string }[];
}

// The committed spec is produced by `npm run spec:build`; skip when it is absent (fresh checkout without the submodule).
const describeSpec = fs.existsSync(SPEC) ? describe : describe.skip;

describeSpec('resolution policy against spec/open-api-spec.yaml', () => {
  const doc = YAML.parse(fs.readFileSync(SPEC, 'utf8')) as Doc;
  const operations = new Set<string>();
  const firstSegments = new Set<string>();
  for (const [p, item] of Object.entries(doc.paths)) {
    for (const m of Object.keys(item)) if (METHODS.includes(m)) operations.add(`${m.toUpperCase()} ${p}`);
    firstSegments.add(p.split('/')[1] ?? '');
  }
  const services = new Set(doc.tags.map((t) => t.name));

  it('every operation hint names an operation of the spec', () => {
    const stale = Object.keys(operationHints).filter((k) => !operations.has(k));
    expect(stale).toEqual([]);
  });

  it('hints use snake_case method names', () => {
    for (const hint of Object.values(operationHints)) expect(hint.name).toMatch(/^[a-z][a-z0-9_]*$/);
  });

  it('every mount rule targets a service of the spec', () => {
    for (const [source, target] of Object.entries(mountRules)) {
      expect(services.has(target), `${source} -> ${target}`).toBe(true);
    }
  });

  it('keeps operationIds verbatim', () => {
    expect(operationIdTransform('getFeatureSKU')).toBe('getFeatureSKU');
  });
});
