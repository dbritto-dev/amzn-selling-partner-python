/**
 * Spec build (step 0 of the pipeline): the one OpenAPI 3 document the
 * generator consumes.
 *
 * Amazon ships the Selling Partner API as 67 Swagger 2.0 files plus 24 JSON
 * Schema files for notification payloads; oagen wants a single OpenAPI 3
 * document. This script converts each file (`convert.ts`), namespaces its
 * components as `<package>:<Name>` (`orders_v0:Order`) so equally named
 * schemas of different API versions never collide, tags every operation with
 * its API version (`OrdersV0`, the oagen service = the SDK resource class) and
 * merges everything into `spec/open-api-spec.yaml`, the committed document
 * every `oagen` command runs against (as in workos/openapi-spec).
 *
 *   npm run spec:build                # Amazon models + notification schemas -> spec/open-api-spec.yaml
 *   npm run spec:build -- --petstore  # tests/fixtures/petstore_*.json      -> spec/petstore.yaml
 *   npm run spec:build -- --only orders
 *
 * The build report (services, conversion warnings) goes to `.build/<name>.report.json`.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import YAML from 'yaml';
import { toOpenApi3, wrapJsonSchema, type JsonObject } from '../convert.js';
import { apiNaming } from '../amazon.js';
import { identifier, pascalCase } from '../python/naming.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..', '..');
const SPEC_DIR = path.resolve(HERE, '..', '..', 'spec');
const BUILD = path.resolve(HERE, '..', '..', '.build');
const MODELS = path.join(ROOT, 'spec', 'selling-partner-api-models', 'models');
const SCHEMAS = path.join(ROOT, 'spec', 'selling-partner-api-models', 'schemas', 'notifications');

function isObject(v: unknown): v is JsonObject {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** Service (oagen) / resource class name of an API version: `orders` + `v0` -> `OrdersV0`. */
export function serviceName(api: string, version: string): string {
  return pascalCase(api) + pascalCase(version.replace(/^v/, 'V'));
}

const COMPONENT_KINDS = ['schemas', 'parameters', 'responses', 'requestBodies', 'headers', 'examples', 'links', 'callbacks', 'securitySchemes'];

/** Rename every component of `doc` to `<pkg>:<name>` and rewrite the references. */
export function namespaceComponents(doc: JsonObject, pkg: string): JsonObject {
  const components = isObject(doc.components) ? doc.components : {};
  const renamed: JsonObject = {};
  for (const kind of COMPONENT_KINDS) {
    const entries = components[kind];
    if (!isObject(entries)) continue;
    const out: JsonObject = {};
    for (const [name, schema] of Object.entries(entries)) out[`${pkg}:${name}`] = schema;
    renamed[kind] = out;
  }
  const rewrite = (node: unknown): unknown => {
    if (Array.isArray(node)) return node.map(rewrite);
    if (!isObject(node)) return node;
    const out: JsonObject = {};
    for (const [k, v] of Object.entries(node)) {
      if (k === '$ref' && typeof v === 'string') {
        const m = /^#\/components\/([a-zA-Z]+)\/(.+)$/.exec(v);
        out[k] = m ? `#/components/${m[1]}/${pkg}:${m[2]}` : v;
      } else if (k === 'discriminator' && isObject(v) && isObject(v.mapping)) {
        const mapping: JsonObject = {};
        for (const [mk, mv] of Object.entries(v.mapping)) {
          const m = typeof mv === 'string' ? /^#\/components\/schemas\/(.+)$/.exec(mv) : null;
          mapping[mk] = m ? `#/components/schemas/${pkg}:${m[1]}` : mv;
        }
        out[k] = { ...v, mapping };
      } else {
        out[k] = rewrite(v);
      }
    }
    return out;
  };
  return { ...doc, paths: rewrite(doc.paths ?? {}), components: rewrite(renamed) };
}

export interface MergeInput {
  document: JsonObject; // OpenAPI 3
  pkg: string; // models package (`orders_v0`)
  service: string; // resource class / oagen service (`OrdersV0`)
  /** Prepended to every path (documents whose paths only differ by server base path). */
  pathPrefix?: string;
}

const METHODS = ['get', 'put', 'post', 'delete', 'options', 'head', 'patch', 'trace'];

/**
 * Amazon's examples contain sample pre-signed S3 URLs whose `X-Amz-Credential`
 * carries a (sample) AWS access key ID; GitHub's push protection rejects any
 * commit that contains one. The examples only document the wire format, so the
 * key IDs are redacted in the committed spec (the sandbox runner reads the
 * examples from the submodule, not from here).
 */
export function redactSampleCredentials(node: unknown): unknown {
  if (typeof node === 'string') return node.replace(/AKIA[0-9A-Z]{16}/g, 'AKIAEXAMPLE');
  if (Array.isArray(node)) return node.map(redactSampleCredentials);
  if (!isObject(node)) return node;
  const out: JsonObject = {};
  for (const [k, v] of Object.entries(node)) out[k] = redactSampleCredentials(v);
  return out;
}

/** Merge namespaced documents into one; every operation is tagged with its service. */
export function mergeDocuments(inputs: MergeInput[], info: JsonObject, servers: JsonObject[]): JsonObject {
  const paths: JsonObject = {};
  const components: JsonObject = {};
  const roots: string[] = [];
  const owner = new Map<string, string>();
  for (const input of inputs) {
    const doc = namespaceComponents(input.document, input.pkg);
    if (typeof input.document['x-root-schema'] === 'string') roots.push(`${input.pkg}:${input.document['x-root-schema']}`);
    for (const [rawPath, item] of Object.entries(isObject(doc.paths) ? doc.paths : {})) {
      if (!isObject(item)) continue;
      const p = (input.pathPrefix ?? '') + rawPath;
      if (owner.has(p)) throw new Error(`path ${p} is defined by both ${owner.get(p)} and ${input.service}`);
      owner.set(p, input.service);
      const out: JsonObject = {};
      for (const [k, v] of Object.entries(item)) {
        out[k] = METHODS.includes(k) && isObject(v) ? { ...v, tags: [input.service] } : v;
      }
      paths[p] = out;
    }
    for (const [kind, entries] of Object.entries(isObject(doc.components) ? doc.components : {})) {
      if (!isObject(entries)) continue;
      components[kind] = { ...(isObject(components[kind]) ? components[kind] : {}), ...entries };
    }
  }
  const out: JsonObject = { openapi: '3.0.3', info, servers, tags: inputs.map((i) => ({ name: i.service })), paths, components };
  if (roots.length) out['x-root-schemas'] = roots;
  return redactSampleCredentials(out) as JsonObject;
}

export interface BuildResult {
  document: JsonObject;
  warnings: string[];
  services: { service: string; pkg: string; operations: number; title: string }[];
}

function countOps(doc: JsonObject): number {
  let n = 0;
  for (const item of Object.values(isObject(doc.paths) ? doc.paths : {})) {
    if (isObject(item)) n += Object.keys(item).filter((k) => METHODS.includes(k)).length;
  }
  return n;
}

export async function buildAmazon(only?: string): Promise<BuildResult> {
  const warnings: string[] = [];
  const inputs: MergeInput[] = [];
  const services: BuildResult['services'] = [];
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
    const pkg = `${api}_${version}`;
    if (seen.has(pkg)) throw new Error(`${file} and ${seen.get(pkg)} both map to ${pkg}`);
    seen.set(pkg, file);
    const converted = await toOpenApi3(raw, path.relative(ROOT, file));
    warnings.push(...converted.warnings);
    const service = serviceName(api, version);
    inputs.push({ document: converted.document, pkg, service });
    services.push({ service, pkg, operations: countOps(converted.document), title: String(info.title ?? api) });
  }
  if (!only && fs.existsSync(SCHEMAS)) {
    for (const f of fs.readdirSync(SCHEMAS).sort()) {
      if (!f.endsWith('.json')) continue;
      const name = path.basename(f, '.json');
      const raw = JSON.parse(fs.readFileSync(path.join(SCHEMAS, f), 'utf8')) as JsonObject;
      const converted = await toOpenApi3(wrapJsonSchema(raw, name), `schemas/notifications/${f}`);
      warnings.push(...converted.warnings);
      // the package keeps the schema file stem (`ListingsItemIssuesChangeNotification_2023_12_13`) so the registry can name it
      inputs.push({ document: converted.document, pkg: `notifications.${identifier(name)}`, service: `Notifications${pascalCase(name)}` });
    }
  }
  const document = mergeDocuments(
    inputs,
    { title: 'Selling Partner API', version: pinnedVersion(), description: 'Amazon Selling Partner API (all API versions of the pinned models).' },
    [{ url: 'https://sellingpartnerapi-na.amazon.com' }],
  );
  return { document, warnings, services };
}

/** The pinned submodule commit (short sha), the same on every checkout; `0` when git is unavailable. */
function pinnedVersion(): string {
  try {
    return execFileSync('git', ['-C', path.join(ROOT, 'spec', 'selling-partner-api-models'), 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim().slice(0, 12);
  } catch {
    return '0';
  }
}

export async function buildPetstore(): Promise<BuildResult> {
  const warnings: string[] = [];
  const inputs: MergeInput[] = [];
  const services: BuildResult['services'] = [];
  for (const [file, api, version] of [
    ['petstore_oas31.json', 'petstore', 'v3'],
    ['petstore_swagger2.json', 'petstore', 'v2'],
  ] as const) {
    const raw = JSON.parse(fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', file), 'utf8')) as JsonObject;
    const converted = await toOpenApi3(raw, `tests/fixtures/${file}`);
    warnings.push(...converted.warnings);
    const service = serviceName(api, version);
    // the two fixtures describe the same paths in two spec formats: mount them side by side
    inputs.push({ document: converted.document, pkg: `${api}_${version}`, service, pathPrefix: `/${version}` });
    services.push({ service, pkg: `${api}_${version}`, operations: countOps(converted.document), title: 'Petstore' });
  }
  const document = mergeDocuments(inputs, { title: 'Petstore', version: '1.0.0' }, [{ url: 'https://petstore.example.com' }]);
  return { document, warnings, services };
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);
  const only = args.includes('--only') ? args[args.indexOf('--only') + 1] : undefined;
  const petstore = args.includes('--petstore');
  const result = petstore ? await buildPetstore() : await buildAmazon(only);
  const name = petstore ? 'petstore' : 'open-api-spec';
  const out = path.join(SPEC_DIR, `${name}.yaml`);
  fs.mkdirSync(SPEC_DIR, { recursive: true });
  fs.mkdirSync(BUILD, { recursive: true });
  fs.writeFileSync(out, YAML.stringify(result.document, { lineWidth: 0, aliasDuplicateObjects: false }));
  fs.writeFileSync(path.join(BUILD, `${name}.report.json`), JSON.stringify({ services: result.services, warnings: result.warnings }, null, 2));
  const ops = result.services.reduce((n, s) => n + s.operations, 0);
  process.stdout.write(`${path.relative(process.cwd(), out)}: ${result.services.length} services, ${ops} operations, ${result.warnings.length} warnings\n`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((err) => {
    process.stderr.write(`${err instanceof Error ? (err.stack ?? err.message) : String(err)}\n`);
    process.exit(1);
  });
}
