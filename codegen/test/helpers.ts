/**
 * Run a spec through the emitter (the same pipeline as `oagen generate` with
 * oagen.config.ts) and return the generated files by path.
 *
 * `parseSpec` takes a file path, so an inline fixture is written to a temp
 * file first (`emitInline`).
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { generateFiles, parseSpec, resolveOperations, type GeneratedFile } from '@workos/oagen';
import config from '../oagen.config.js';
import { pythonEmitter } from '../src/python/index.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
export const TASKS_SPEC = path.join(ROOT, 'tests', 'fixtures', 'tasks-api.yml');

export async function emit(specPath: string, namespace = 'TasksClient'): Promise<Record<string, string>> {
  const spec = await parseSpec(specPath, {
    schemaNameTransform: config.schemaNameTransform,
    operationIdTransform: config.operationIdTransform,
    transformSpec: config.transformSpec,
  });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'codegen-test-'));
  try {
    const { files } = generateFiles(spec, pythonEmitter, {
      namespace,
      outputDir: dir,
      operationHints: config.operationHints,
      mountRules: config.mountRules,
      emitterOptions: config.emitterOptions?.python,
    });
    return Object.fromEntries(files.map((f: GeneratedFile) => [f.path, f.content]));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

/** Emit an inline YAML spec (written to a temp file, as `parseSpec` wants a path). */
export async function emitInline(yaml: string, namespace = 'Client'): Promise<Record<string, string>> {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'codegen-spec-'));
  const file = path.join(dir, 'spec.yml');
  fs.writeFileSync(file, yaml);
  try {
    return await emit(file, namespace);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}

export { resolveOperations };
