/**
 * Spec transforms of the resolution policy: `OagenConfig.transformSpec`,
 * `schemaNameTransform` and `operationIdTransform`.
 *
 * `transformSpec` is the pre-IR overlay that keeps oagen's parser from losing
 * information present in the Amazon files (docs/PLAN.md):
 *
 * 1. Named schemas that are not objects (`OrderList: array of Order`,
 *    `MarketplaceId: string`, bare `oneOf` unions) are inlined at every
 *    reference site; oagen would otherwise turn them into empty models.
 * 2. Inline object schemas are hoisted to named components (`<Parent><Field>`).
 * 3. Every component schema name is replaced by a guard token (`X17`) so that
 *    oagen's `cleanSchemaName` (which singularises the first word and re-cases
 *    acronyms: `OrdersList` -> `OrderList`, `ASINIdentifier` -> `AsinIdentifier`)
 *    leaves it alone; `schemaNameTransform` maps the token back.
 */
import type { JsonObject } from '../convert.js';

export const NAME_GUARD = 'X';

/**
 * Guard token -> original component name for the document transformed last.
 * oagen runs `cleanSchemaName(toPascalCase(name))` on every component name,
 * which rewrites acronyms (`ASINIdentifier` -> `AsinIdentifier`) and digit
 * boundaries; a token of the form `X<n>` survives both untouched, so the
 * original name can be restored by `schemaNameTransform`.
 */
const NAME_MAP = new Map<string, string>();

export function guardName(name: string): string {
  for (const [token, original] of NAME_MAP) if (original === name) return token;
  const token = `${NAME_GUARD}${NAME_MAP.size + 1}`;
  NAME_MAP.set(token, name);
  return token;
}

function isObject(v: unknown): v is JsonObject {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

export function isAliasSchema(s: unknown): s is JsonObject {
  if (!isObject(s)) return false;
  if (s.$ref || s.properties || s.allOf || s.enum) return false;
  // a bare oneOf/anyOf component would become an empty model: inline it as a union
  if ((Array.isArray(s.oneOf) || Array.isArray(s.anyOf)) && s.type === undefined) return true;
  if (s.oneOf || s.anyOf) return false;
  if (s.type === 'object' || (s.type === undefined && s.additionalProperties !== undefined)) return true; // free-form or map
  return ['array', 'string', 'integer', 'number', 'boolean'].includes(String(s.type));
}

export interface TransformReport {
  inlined: string[];
}

function pascal(name: string): string {
  return name
    .replace(/[^0-9a-zA-Z_]+/g, '_')
    .split('_')
    .filter(Boolean)
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join('');
}

function isInlineObject(s: unknown): boolean {
  // a stray `properties` next to `type: array` (seen in the notification schemas) does not make an object
  return (
    isObject(s) &&
    !s.$ref &&
    (s.type === 'object' || s.type === undefined) &&
    isObject(s.properties) &&
    Object.keys(s.properties).length > 0 &&
    !s.allOf &&
    !s.oneOf &&
    !s.anyOf
  );
}

/**
 * Hoist inline object schemas (nested `properties`, array `items`) into named
 * components (`<Parent><Field>`, `<Parent><Field>Item`) so that oagen never has
 * to synthesise a model name (its synthesised names do not always match the
 * references it emits for them, which surfaces as "Unresolved model reference").
 */
export function liftInlineObjects(schemas: JsonObject): JsonObject {
  const out: JsonObject = { ...schemas };
  const unique = (base: string): string => {
    let name = base;
    let n = 2;
    while (name in out) name = `${base}${n++}`;
    return name;
  };
  const lift = (schema: JsonObject, parent: string): JsonObject => {
    const props = isObject(schema.properties) && schema.type !== 'array' ? schema.properties : undefined;
    if (!props) return schema;
    const newProps: JsonObject = {};
    for (const [field, raw] of Object.entries(props)) {
      newProps[field] = liftValue(raw, `${parent}${pascal(field)}`);
    }
    const ap = schema.additionalProperties;
    const newAp = ap !== undefined && ap !== null && typeof ap === 'object' ? liftValue(ap, `${parent}Value`) : ap;
    return { ...schema, properties: newProps, ...(newAp !== undefined ? { additionalProperties: newAp } : {}) };
  };
  const liftValue = (raw: unknown, name: string): unknown => {
    if (!isObject(raw)) return raw;
    if (isInlineObject(raw)) {
      const { description, ...rest } = raw;
      const compName = unique(name);
      out[compName] = lift(rest, compName);
      return description !== undefined ? { $ref: `#/components/schemas/${compName}`, description } : { $ref: `#/components/schemas/${compName}` };
    }
    if (raw.type === 'array' && isObject(raw.items)) {
      return { ...raw, items: liftValue(raw.items, `${name}Item`) };
    }
    for (const key of ['oneOf', 'anyOf', 'allOf'] as const) {
      const variants: unknown = raw[key];
      if (Array.isArray(variants)) {
        return { ...raw, [key]: variants.map((v: unknown, i: number) => liftValue(v, `${name}${key === 'allOf' ? 'Part' : 'Variant'}${i + 1}`)) };
      }
    }
    return raw;
  };
  for (const [name, schema] of Object.entries(schemas)) {
    if (isObject(schema)) out[name] = lift(schema, name);
  }
  return out;
}

export function transformSpec(doc: JsonObject, report?: TransformReport): JsonObject {
  const components = isObject(doc.components) ? doc.components : {};
  const schemas = liftInlineObjects(isObject(components.schemas) ? components.schemas : {});
  NAME_MAP.clear();
  const aliases: Record<string, JsonObject> = {};
  const roots = new Set<string>(typeof doc['x-root-schema'] === 'string' ? [doc['x-root-schema']] : []);
  if (Array.isArray(doc['x-root-schemas'])) for (const r of doc['x-root-schemas']) if (typeof r === 'string') roots.add(r);
  for (const [k, v] of Object.entries(schemas)) if (!roots.has(k) && isAliasSchema(v)) aliases[k] = v; // the root of a JSON-Schema document stays a model
  report?.inlined.push(...Object.keys(aliases));

  const walk = (node: unknown, depth = 0): unknown => {
    if (depth > 200) throw new Error('transformSpec: reference cycle through alias schemas');
    if (Array.isArray(node)) return node.map((v) => walk(v, depth));
    if (!isObject(node)) return node;
    if (typeof node.$ref === 'string' && node.$ref.startsWith('#/components/schemas/')) {
      const name = node.$ref.slice('#/components/schemas/'.length);
      const alias = aliases[name];
      if (alias) {
        // keep the sibling description (OAS 3.0 ignores siblings of $ref, but oagen reads them)
        const { $ref: _ref, ...siblings } = node;
        return walk({ ...structuredClone(alias), ...siblings }, depth + 1);
      }
      return { ...node, $ref: `#/components/schemas/${guardName(name)}` };
    }
    const out: JsonObject = {};
    for (const [k, v] of Object.entries(node)) {
      if (k === 'discriminator' && isObject(v) && isObject(v.mapping)) {
        const mapping: JsonObject = {};
        for (const [mk, mv] of Object.entries(v.mapping)) {
          mapping[mk] = typeof mv === 'string' && mv.startsWith('#/components/schemas/') ? `#/components/schemas/${guardName(mv.slice('#/components/schemas/'.length))}` : mv;
        }
        out[k] = { ...v, mapping };
        continue;
      }
      out[k] = walk(v, depth);
    }
    return out;
  };

  const newSchemas: JsonObject = {};
  for (const [k, v] of Object.entries(schemas)) {
    if (aliases[k]) continue;
    newSchemas[guardName(k)] = walk(v);
  }
  const otherComponents: JsonObject = {};
  for (const [k, v] of Object.entries(components)) if (k !== 'schemas') otherComponents[k] = walk(v);
  const out: JsonObject = { ...doc, paths: walk(doc.paths ?? {}), components: { ...otherComponents, schemas: newSchemas } };
  if (typeof doc['x-root-schema'] === 'string' && aliases[doc['x-root-schema']] === undefined) {
    out['x-root-schema'] = doc['x-root-schema'];
  }
  return out;
}

/** Restore the original component name behind a guard token (see `NAME_MAP`). */
export function schemaNameTransform(name: string): string {
  return NAME_MAP.get(name) ?? name;
}

/**
 * Keep operationIds verbatim (oagen would camelCase `getFeatureSKU`): they key
 * Amazon's documentation, the RDT tables, the `OPERATIONS` registry and the
 * sandbox examples.
 */
export function operationIdTransform(id: string): string {
  return id;
}
