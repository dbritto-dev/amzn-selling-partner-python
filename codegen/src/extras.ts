/**
 * Facts the oagen IR does not carry, read straight from the converted OpenAPI
 * document (shared by the driver and oagen.config.ts).
 */
import type { JsonObject } from './convert.js';
import type { OperationExtras, UnionAlias } from './python/options.js';

function isObject(v: unknown): v is JsonObject {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** Component schemas that are a bare oneOf/anyOf of references (oagen emits them as empty models). */
export function extractUnionAliases(doc: JsonObject): Record<string, UnionAlias> {
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
export function extractExtras(doc: JsonObject): Record<string, OperationExtras> {
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
