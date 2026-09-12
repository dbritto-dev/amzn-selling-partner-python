/**
 * Swagger 2.0 -> OpenAPI 3.0 conversion (in memory) with the fixes the pinned
 * Amazon files need before oagen can parse them. Nothing here is Amazon
 * specific except the list of known-bad references; a well-formed document
 * passes through untouched.
 */
import converter from 'swagger2openapi';

export type JsonObject = Record<string, unknown>;

export interface ConvertResult {
  document: JsonObject;
  warnings: string[];
}

function isObject(v: unknown): v is JsonObject {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** Collect every `$ref` (and the `#ref` typo) in a document. */
function collectRefs(node: unknown, out: Set<string>): void {
  if (Array.isArray(node)) {
    for (const v of node) collectRefs(v, out);
  } else if (isObject(node)) {
    for (const [k, v] of Object.entries(node)) {
      if ((k === '$ref' || k === '#ref') && typeof v === 'string') out.add(v);
      else collectRefs(v, out);
    }
  }
}

/**
 * Repair the two irregularities found in the pinned models:
 * `#ref` instead of `$ref`, and references to definitions that do not exist
 * (replaced by an empty schema, with a warning).
 */
export function repairDocument(doc: JsonObject, warnings: string[], label: string): JsonObject {
  const definitions = isObject(doc.definitions) ? doc.definitions : isObject(doc.components) && isObject(doc.components.schemas) ? doc.components.schemas : {};
  const prefix = doc.swagger ? '#/definitions/' : '#/components/schemas/';
  const walk = (node: unknown): unknown => {
    if (Array.isArray(node)) return node.map(walk);
    if (!isObject(node)) return node;
    const out: JsonObject = {};
    for (const [k, v] of Object.entries(node)) {
      if (k === '#ref' && typeof v === 'string') {
        warnings.push(`${label}: '#ref' typo repaired (${v})`);
        out.$ref = v;
        continue;
      }
      out[k] = walk(v);
    }
    if (typeof out.$ref === 'string' && out.$ref.startsWith(prefix)) {
      const name = out.$ref.slice(prefix.length);
      if (!(name in definitions)) {
        warnings.push(`${label}: dangling reference ${out.$ref} replaced by an empty schema`);
        delete out.$ref;
        if (out.description === undefined) out.description = `(unresolved reference ${name})`;
      }
    }
    return out;
  };
  return walk(doc) as JsonObject;
}

export async function toOpenApi3(raw: JsonObject, label: string): Promise<ConvertResult> {
  const warnings: string[] = [];
  const repaired = repairDocument(raw, warnings, label);
  if (typeof repaired.openapi === 'string') {
    return { document: repaired, warnings };
  }
  if (repaired.swagger !== '2.0') {
    throw new Error(`${label}: not a Swagger 2.0 or OpenAPI 3.x document`);
  }
  const result = await converter.convertObj(repaired as never, { patch: true, warnOnly: true, resolve: false, direct: false });
  for (const w of result.warnings ?? []) warnings.push(`${label}: swagger2openapi: ${String((w as { message?: string }).message ?? w)}`);
  return { document: result.openapi as JsonObject, warnings };
}

/** Wrap a standalone JSON Schema (notification payloads) into an OpenAPI 3 document. */
export function wrapJsonSchema(schema: JsonObject, name: string): JsonObject {
  const rootName = typeof schema.title === 'string' && /^[A-Za-z][A-Za-z0-9]*$/.test(schema.title) ? schema.title : name;
  const { definitions, $defs, ...root } = schema;
  const schemas: JsonObject = {};
  for (const src of [definitions, $defs]) {
    if (isObject(src)) for (const [k, v] of Object.entries(src)) schemas[k] = v;
  }
  schemas[rootName] = root;
  const rewrite = (node: unknown): unknown => {
    if (Array.isArray(node)) return node.map(rewrite);
    if (!isObject(node)) return node;
    const out: JsonObject = {};
    for (const [k, v] of Object.entries(node)) {
      if ((k === '$ref' || k === '#ref') && typeof v === 'string') {
        out[k] = v.replace(/^#\/(definitions|\$defs)\//, '#/components/schemas/'); // `#ref` typos are repaired later
      } else if (k === '$schema' || k === '$id' || k === 'id') {
        continue;
      } else {
        out[k] = rewrite(v);
      }
    }
    return out;
  };
  return {
    openapi: '3.0.3',
    info: { title: rootName, version: 'notifications' },
    paths: {},
    components: { schemas: rewrite(schemas) as JsonObject },
    'x-root-schema': rootName,
  };
}

export { collectRefs };
