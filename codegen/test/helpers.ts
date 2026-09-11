/** Run a fixture spec through the same pipeline as the driver and return the emitted files by path. */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import YAML from 'yaml';
import { generateFiles, parseSpec } from '@workos/oagen';
import { toOpenApi3, type JsonObject } from '../src/convert.js';
import { extractExtras, extractUnionAliases } from '../src/extras.js';
import { pythonEmitter, resourceClassName } from '../src/python/index.js';
import type { EmitterOptions } from '../src/python/options.js';
import { schemaNameTransform, transformSpec } from '../src/transform.js';

const FIXTURES = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'tests', 'fixtures');

export const TASKS_SPEC = path.join(FIXTURES, 'tasks-api.yml');

export function loadSpec(file: string): JsonObject {
  const text = fs.readFileSync(file, 'utf8');
  return (/\.ya?ml$/.test(file) ? YAML.parse(text) : JSON.parse(text)) as JsonObject;
}

export async function emit(file: string, api: string, version: string, extra: Partial<EmitterOptions> = {}): Promise<Record<string, string>> {
  const { document } = await toOpenApi3(loadSpec(file), path.basename(file));
  const options: EmitterOptions = {
    packageName: 'sdk',
    runtimePackage: 'amzn_selling_partner',
    api,
    version,
    amazon: false,
    extras: extractExtras(document),
    unionAliases: extractUnionAliases(document),
    ...extra,
  };
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'codegen-test-'));
  try {
    const specPath = path.join(dir, 'spec.json');
    fs.writeFileSync(specPath, JSON.stringify(transformSpec(document)));
    const spec = await parseSpec(specPath, { schemaNameTransform, operationIdTransform: (id) => id });
    const { files } = generateFiles(spec, pythonEmitter, {
      namespace: resourceClassName(api, version),
      outputDir: path.join(dir, 'out'),
      emitterOptions: options as unknown as Record<string, unknown>,
    });
    return Object.fromEntries(files.map((f) => [f.path, f.content]));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}
