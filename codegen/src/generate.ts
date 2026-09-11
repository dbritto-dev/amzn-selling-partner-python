/**
 * Driver: turn every pinned spec into generated Python.
 *
 *   npm run generate                 # Amazon models + notification schemas + the petstore test package
 *   npm run generate -- --only orders
 *
 * Per model file: read -> Swagger 2.0 -> OpenAPI 3 (`convert.ts`) -> pre-IR
 * fixes (`transform.ts`) -> `parseSpec` (oagen) -> `generateFiles` (oagen +
 * `emitter/`) -> files under src/amzn_selling_partner/{models,resources}.
 * `apis.py` is written once from the collected registry.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { generateFiles, parseSpec, type ApiSpec, type GeneratedFile } from '@workos/oagen';
import { toOpenApi3, wrapJsonSchema, type JsonObject } from './convert.js';
import { schemaNameTransform, transformSpec } from './transform.js';
import { pythonEmitter, resourceClassName } from './emitter/index.js';
import { renderApisModule, type ApiVersionEntry } from './emitter/apis.js';
import { newReport, type EmitterOptions, type OperationExtras, type UnionAlias } from './emitter/options.js';
import { ALIASES, apiNaming, compareVersions, DROP_PARAMS_ON_NEXT, paginationOverride } from './amazon.js';
import { className, snakeCase, pyStr } from './emitter/naming.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const BUILD = path.resolve(HERE, '..', '.build');
const MODELS = path.join(ROOT, 'spec', 'selling-partner-api-models', 'models');
const SCHEMAS = path.join(ROOT, 'spec', 'selling-partner-api-models', 'schemas', 'notifications');
const PACKAGE = 'amzn_selling_partner';
const SRC = path.join(ROOT, 'src', PACKAGE);

const args = process.argv.slice(2);
const only = args.includes('--only') ? args[args.indexOf('--only') + 1] : undefined;
const skipFormat = args.includes('--no-format');
const skipAmazon = args.includes('--skip-amazon');

function isObject(v: unknown): v is JsonObject {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** Component schemas that are a bare oneOf/anyOf of references (oagen emits them as empty models). */
function extractUnionAliases(doc: JsonObject): Record<string, UnionAlias> {
  const out: Record<string, UnionAlias> = {};
  const schemas = isObject(doc.components) && isObject(doc.components.schemas) ? doc.components.schemas : {};
  for (const [name, schema] of Object.entries(schemas)) {
    if (!isObject(schema) || schema.properties || schema.allOf) continue;
    const variants = (schema.oneOf ?? schema.anyOf) as unknown;
    if (!Array.isArray(variants) || variants.length === 0) continue;
    const refs = variants.map((v: unknown) => (isObject(v) && typeof v.$ref === 'string' ? v.$ref.split('/').pop()! : null));
    if (refs.some((r) => r === null)) continue;
    const disc = isObject(schema.discriminator) && typeof schema.discriminator.propertyName === 'string' ? schema.discriminator.propertyName : undefined;
    out[name] = { variants: refs as string[], discriminator: disc, description: typeof schema.description === 'string' ? schema.description : undefined };
  }
  return out;
}

/** Facts the IR drops, read straight from the converted document. */
function extractExtras(doc: JsonObject): Record<string, OperationExtras> {
  const out: Record<string, OperationExtras> = {};
  const paths = isObject(doc.paths) ? doc.paths : {};
  for (const [p, item] of Object.entries(paths)) {
    if (!isObject(item)) continue;
    const shared = Array.isArray(item.parameters) ? item.parameters : [];
    for (const [method, op] of Object.entries(item)) {
      if (!isObject(op) || !['get', 'put', 'post', 'delete', 'patch', 'head', 'options', 'trace'].includes(method)) continue;
      const extras: OperationExtras = {};
      if (isObject(op.requestBody)) extras.bodyRequired = op.requestBody.required === true;
      const codes: Record<string, boolean> = {};
      const media: Record<string, string[]> = {};
      for (const [code, resp] of Object.entries(isObject(op.responses) ? op.responses : {})) {
        if (!/^2\d\d$/.test(code) || !isObject(resp)) continue;
        const content = isObject(resp.content) ? resp.content : {};
        codes[code] = Object.values(content).some((m) => isObject(m) && m.schema !== undefined);
        media[code] = Object.keys(content);
      }
      extras.successCodes = codes;
      extras.successMedia = media;
      const params = [...shared, ...(Array.isArray(op.parameters) ? op.parameters : [])];
      const greedy = params.filter((x) => isObject(x) && x.in === 'path' && x['x-amazon-spds-greedy-path-parameter']).map((x) => String((x as JsonObject).name));
      if (greedy.length) extras.greedyPathParams = greedy;
      if (typeof op.summary === 'string' && op.summary.trim()) extras.summary = op.summary;
      const dflt = isObject(op.responses) && isObject(op.responses.default) ? op.responses.default : undefined;
      const dfltSchema = dflt && isObject(dflt.content) ? Object.values(dflt.content).map((m) => (isObject(m) && isObject(m.schema) ? m.schema : undefined)).find(Boolean) : undefined;
      if (dfltSchema && typeof dfltSchema.$ref === 'string') extras.defaultErrorRef = dfltSchema.$ref.split('/').pop();
      out[`${method.toUpperCase()} ${p}`] = extras;
    }
  }
  return out;
}

interface Target {
  packageName: string;
  srcDir: string; // directory of the python package
  amazon: boolean;
}

interface Generated {
  entry: ApiVersionEntry;
  files: GeneratedFile[];
}

async function generateOne(
  raw: JsonObject,
  label: string,
  api: string,
  version: string,
  target: Target,
  warnings: string[],
  rootSchema?: string,
): Promise<Generated> {
  const converted = await toOpenApi3(raw, label);
  warnings.push(...converted.warnings);
  const extras = extractExtras(converted.document);
  const unionAliases = extractUnionAliases(converted.document);
  const transformed = transformSpec(converted.document);
  fs.mkdirSync(path.join(BUILD, 'specs'), { recursive: true });
  const specPath = path.join(BUILD, 'specs', `${target.packageName}__${api}__${version}.json`);
  fs.writeFileSync(specPath, JSON.stringify(transformed, null, 1));
  // keep operationIds verbatim (oagen would camelCase `getFeatureSKU` -> `getFeatureSku`); method names are derived from them
  const spec: ApiSpec = await parseSpec(specPath, { schemaNameTransform, operationIdTransform: (id) => id });
  const report = newReport();
  const opts: EmitterOptions = {
    packageName: target.packageName,
    runtimePackage: PACKAGE,
    api,
    version,
    amazon: target.amazon,
    extras,
    unionAliases,
    rootSchema,
    report,
    paginationOverride: target.amazon ? (opId) => paginationOverride(api, version, opId) : undefined,
    dropParamsOnNext: target.amazon ? (opId) => DROP_PARAMS_ON_NEXT.has(`${api}.${opId}`) : undefined,
  };
  const emitter = pythonEmitter(opts);
  const { files } = generateFiles(spec, emitter, { namespace: resourceClassName(api, version), outputDir: path.join(BUILD, 'out') });
  reports[`${target.packageName}.${api}.${version}`] = report;
  const operations = spec.services.reduce((n, s) => n + s.operations.length, 0);
  return { entry: { api, version, title: spec.name, operations }, files };
}

const reports: Record<string, ReturnType<typeof newReport>> = {};

function writeFiles(target: Target, files: GeneratedFile[]): string[] {
  const written: string[] = [];
  for (const f of files) {
    const dest = path.join(target.srcDir, f.path);
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.writeFileSync(dest, f.content);
    written.push(dest);
  }
  return written;
}

function writeInits(target: Target, entries: ApiVersionEntry[], extraDirs: string[] = []): string[] {
  const written: string[] = [];
  const apis = [...new Set(entries.map((e) => e.api))].sort();
  for (const kind of ['models', 'resources']) {
    const dir = path.join(target.srcDir, kind);
    fs.mkdirSync(dir, { recursive: true });
    const init = path.join(dir, '__init__.py');
    fs.writeFileSync(init, `"""Generated ${kind} (codegen/, oagen). Do not edit by hand."""\n`);
    written.push(init);
    for (const api of apis) {
      const sub = path.join(dir, api, '__init__.py');
      if (!fs.existsSync(path.dirname(sub))) continue;
      fs.writeFileSync(sub, `"""Generated ${kind} for the ${api} API. Do not edit by hand."""\n`);
      written.push(sub);
    }
  }
  for (const d of extraDirs) {
    const init = path.join(target.srcDir, d, '__init__.py');
    if (fs.existsSync(path.dirname(init)) && !fs.existsSync(init)) {
      fs.writeFileSync(init, '"""Generated (codegen/, oagen). Do not edit by hand."""\n');
      written.push(init);
    }
  }
  return written;
}

function resetGenerated(target: Target): void {
  for (const kind of ['models', 'resources']) fs.rmSync(path.join(target.srcDir, kind), { recursive: true, force: true });
  fs.rmSync(path.join(target.srcDir, 'apis.py'), { force: true });
}

async function generateAmazon(warnings: string[]): Promise<string[]> {
  const target: Target = { packageName: PACKAGE, srcDir: SRC, amazon: true };
  resetGenerated(target);
  const entries: ApiVersionEntry[] = [];
  const written: string[] = [];
  const files: string[] = [];
  for (const dir of fs.readdirSync(MODELS).sort()) {
    const full = path.join(MODELS, dir);
    if (!fs.statSync(full).isDirectory()) continue;
    for (const f of fs.readdirSync(full).sort()) if (f.endsWith('.json')) files.push(path.join(full, f));
  }
  const seen = new Map<string, string>();
  for (const file of files) {
    if (only && !file.includes(only)) continue;
    const raw = JSON.parse(fs.readFileSync(file, 'utf8')) as JsonObject;
    const info = isObject(raw.info) ? raw.info : {};
    const [api, version] = apiNaming(path.basename(file, '.json'), typeof info.version === 'string' ? info.version : undefined);
    const key = `${api}.${version}`;
    if (seen.has(key)) throw new Error(`${file} and ${seen.get(key)} both map to ${key}`);
    seen.set(key, file);
    const g = await generateOne(raw, path.relative(ROOT, file), api, version, target, warnings);
    entries.push(g.entry);
    written.push(...writeFiles(target, g.files));
    process.stdout.write(`${key}: ${g.entry.operations} operations\n`);
  }
  if (!only) written.push(...(await generateNotifications(target, warnings)));
  const apisPath = path.join(SRC, 'apis.py');
  fs.writeFileSync(apisPath, renderApisModule({ packageName: PACKAGE, runtimePackage: PACKAGE, entries, aliases: ALIASES, compareVersions }));
  written.push(apisPath, ...writeInits(target, entries));
  return written;
}

/** Notification payload schemas -> models/notification_payloads/<name>.py + registry. */
async function generateNotifications(target: Target, warnings: string[]): Promise<string[]> {
  if (!fs.existsSync(SCHEMAS)) return [];
  const written: string[] = [];
  const registry: { name: string; module: string; root: string; types: string[]; versions: (string | null)[] }[] = [];
  for (const f of fs.readdirSync(SCHEMAS).sort()) {
    if (!f.endsWith('.json')) continue;
    const name = path.basename(f, '.json');
    const raw = JSON.parse(fs.readFileSync(path.join(SCHEMAS, f), 'utf8')) as JsonObject;
    const doc = wrapJsonSchema(raw, name);
    const rootRaw = String(doc['x-root-schema']);
    const root = className(rootRaw); // the class name the emitter gives the root schema
    const module = snakeCase(name);
    const g = await generateOne(doc, `schemas/notifications/${f}`, 'notification_payloads', module, target, warnings, rootRaw);
    written.push(...writeFiles(target, g.files));
    const props = isObject(raw.properties) ? raw.properties : {};
    const nt = isObject(props.NotificationType) ? props.NotificationType : {};
    const pv = isObject(props.PayloadVersion) ? props.PayloadVersion : {};
    const examplesOf = (s: JsonObject): string[] =>
      typeof s.example === 'string' ? [s.example] : Array.isArray(s.examples) ? s.examples.filter((x): x is string => typeof x === 'string') : [];
    const types: string[] = [];
    if (Array.isArray(nt.enum)) types.push(...nt.enum.map(String));
    if (typeof nt.const === 'string') types.push(nt.const);
    if (types.length === 0) types.push(...examplesOf(nt));
    let versions: (string | null)[] = [null];
    if (Array.isArray(pv.enum)) versions = pv.enum.map(String);
    else if (pv.const !== undefined) versions = [String(pv.const)];
    else if (examplesOf(pv).length) versions = [...examplesOf(pv), null];
    registry.push({ name, module, root, types, versions });
  }
  const lines: string[] = [];
  lines.push('"""Notification payload models (schemas/notifications/*.json).');
  lines.push('');
  lines.push('Generated by codegen/ (oagen); do not edit by hand.');
  lines.push('"""');
  lines.push('');
  lines.push('from __future__ import annotations');
  lines.push('');
  lines.push('#: schema file stem -> (module, root model class)');
  lines.push('SCHEMAS: dict[str, tuple[str, str]] = {');
  for (const r of registry) lines.push(`    ${pyStr(r.name)}: (${pyStr(r.module)}, ${pyStr(r.root)}),`);
  lines.push('}');
  lines.push('');
  lines.push('#: (NotificationType, PayloadVersion or None) -> schema file stem');
  lines.push('INDEX: dict[tuple[str, str | None], str] = {');
  const seen = new Set<string>();
  for (const r of registry) {
    for (const t of r.types) {
      for (const v of r.versions) {
        const k = `${t}|${v ?? ''}`;
        if (seen.has(k)) continue;
        seen.add(k);
        lines.push(`    (${pyStr(t)}, ${v === null ? 'None' : pyStr(v)}): ${pyStr(r.name)},`);
      }
    }
  }
  lines.push('}');
  lines.push('');
  lines.push('__all__ = ["INDEX", "SCHEMAS"]');
  lines.push('');
  const init = path.join(target.srcDir, 'models', 'notification_payloads', '__init__.py');
  fs.mkdirSync(path.dirname(init), { recursive: true });
  fs.writeFileSync(init, lines.join('\n'));
  written.push(init);
  return written;
}

/** The two petstore fixtures -> tests/petstore_sdk (the generic, non-Amazon path). */
async function generatePetstore(warnings: string[]): Promise<string[]> {
  const target: Target = { packageName: 'petstore_sdk', srcDir: path.join(ROOT, 'tests', 'petstore_sdk'), amazon: false };
  resetGenerated(target);
  const entries: ApiVersionEntry[] = [];
  const written: string[] = [];
  for (const [file, api, version] of [
    ['petstore_oas31.json', 'petstore', 'v3'],
    ['petstore_swagger2.json', 'petstore', 'v2'],
  ] as const) {
    const raw = JSON.parse(fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', file), 'utf8')) as JsonObject;
    const g = await generateOne(raw, `tests/fixtures/${file}`, api, version, target, warnings);
    entries.push(g.entry);
    written.push(...writeFiles(target, g.files));
  }
  const apisPath = path.join(target.srcDir, 'apis.py');
  fs.writeFileSync(apisPath, renderApisModule({ packageName: 'petstore_sdk', runtimePackage: PACKAGE, entries, aliases: { pets: 'petstore' }, compareVersions }));
  const init = path.join(target.srcDir, '__init__.py');
  fs.writeFileSync(init, '"""Generated test package (codegen/, oagen) from tests/fixtures. Do not edit by hand."""\n');
  const clientPath = path.join(target.srcDir, 'client.py');
  fs.writeFileSync(
    clientPath,
    [
      '"""Generated clients over the petstore fixtures (codegen/, oagen). Do not edit by hand."""',
      '',
      'from __future__ import annotations',
      '',
      'from typing import Any',
      '',
      `from ${PACKAGE}.runtime._base_client import AsyncAPIClient, SyncAPIClient`,
      'from petstore_sdk.apis import APIs, AsyncAPIs',
      '',
      '',
      'class Client(SyncAPIClient, APIs):',
      '    _package = "petstore_sdk"',
      '',
      '    def __init__(self, *, base_url: str, **kwargs: Any) -> None:',
      '        super().__init__(base_url=base_url, **kwargs)',
      '',
      '',
      'class AsyncClient(AsyncAPIClient, AsyncAPIs):',
      '    _package = "petstore_sdk"',
      '',
      '    def __init__(self, *, base_url: str, **kwargs: Any) -> None:',
      '        super().__init__(base_url=base_url, **kwargs)',
      '',
      '',
      '__all__ = ["AsyncClient", "Client"]',
      '',
    ].join('\n'),
  );
  written.push(apisPath, init, clientPath, ...writeInits(target, entries));
  return written;
}

function format(files: string[]): void {
  if (skipFormat || files.length === 0) return;
  const py = files.filter((f) => f.endsWith('.py'));
  const cmd = fs.existsSync(path.join(ROOT, '.venv', 'bin', 'ruff')) ? path.join(ROOT, '.venv', 'bin', 'ruff') : 'ruff';
  try {
    execFileSync(cmd, ['check', '--fix', '--select', 'I,F401', '--quiet', ...py], { cwd: ROOT, stdio: 'inherit' });
    execFileSync(cmd, ['format', '--quiet', ...py], { cwd: ROOT, stdio: 'inherit' });
  } catch (err) {
    process.stderr.write(`ruff format failed (${String(err)}); generated files are unformatted\n`);
  }
}

async function main(): Promise<void> {
  const warnings: string[] = [];
  fs.mkdirSync(BUILD, { recursive: true });
  const written = skipAmazon ? [] : await generateAmazon(warnings);
  if (!only) written.push(...(await generatePetstore(warnings)));
  format(written);
  const summary = {
    generatedFiles: written.length,
    warnings,
    unparsedRateLimits: Object.fromEntries(Object.entries(reports).map(([k, r]) => [k, r.unparsedRateLimits]).filter((e) => (e[1] as string[]).length > 0)),
    pagination: Object.assign({}, ...Object.values(reports).map((r) => r.pagination)) as Record<string, string>,
    notes: Object.values(reports).flatMap((r) => r.notes),
  };
  fs.writeFileSync(path.join(BUILD, 'report.json'), JSON.stringify(summary, null, 2));
  const paginated = Object.keys(summary.pagination).length;
  const unparsed = Object.values(summary.unparsedRateLimits as Record<string, string[]>).reduce((n, v) => n + v.length, 0);
  process.stdout.write(`\n${written.length} files written; ${paginated} paginated operations; ${unparsed} operations without a rate-limit table; ${warnings.length} spec warnings (see codegen/.build/report.json)\n`);
}

main().catch((err) => {
  process.stderr.write(`${err instanceof Error ? (err.stack ?? err.message) : String(err)}\n`);
  process.exit(1);
});
