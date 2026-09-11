/** IR TypeRef -> Python type expression. */
import type { TypeRef, PrimitiveType, EnumRef, ApiSpec } from '@workos/oagen';
import { mapTypeRef } from '@workos/oagen';
import { className } from './naming.js';

export interface TypeContext {
  /** Prefix for model/enum names (e.g. "models." from a resource module, "" inside the models module). */
  prefix: string;
  /** Model and enum names that exist in the spec (unknown refs fall back to Any). */
  known: Set<string>;
  /** Enum names that collide with a model name are emitted as `<Name>Enum`. */
  enumNames: Map<string, string>;
  /** Quote model names (forward references inside the models module). */
  quote?: boolean;
}

export function typeContext(spec: ApiSpec, prefix: string, quote = false): TypeContext {
  const known = new Set<string>();
  const models = new Set<string>();
  for (const m of spec.models) {
    known.add(m.name);
    models.add(m.name);
  }
  const enumNames = new Map<string, string>();
  for (const e of spec.enums) {
    known.add(e.name);
    enumNames.set(e.name, models.has(e.name) ? `${e.name}Enum` : e.name);
  }
  return { prefix, known, enumNames, quote };
}

/** Python name of an enum alias (see `TypeContext.enumNames`). */
export function enumAlias(ctx: TypeContext, name: string): string {
  return className(ctx.enumNames.get(name) ?? name);
}

function primitive(r: PrimitiveType): string {
  switch (r.type) {
    case 'string':
      if (r.format === 'date-time' || r.format === 'dateTime') return 'datetime.datetime';
      if (r.format === 'date') return 'datetime.date';
      if (r.format === 'byte' || r.format === 'binary') return 'bytes';
      return 'str';
    case 'integer':
      return 'int';
    case 'number':
      return 'float';
    case 'boolean':
      return 'bool';
    case 'unknown':
      return 'Any';
  }
}

function enumExpr(r: EnumRef, ctx: TypeContext): string {
  if (ctx.enumNames.has(r.name)) return ctx.prefix + enumAlias(ctx, r.name);
  if (r.values && r.values.length) return 'Literal[' + r.values.map((v) => JSON.stringify(v)).join(', ') + ']';
  return 'str';
}

function dedupe(parts: string[]): string[] {
  return [...new Set(parts)];
}

export function pyType(ref: TypeRef, ctx: TypeContext): string {
  return mapTypeRef<string>(ref, {
    primitive,
    array: (_r, items) => `list[${items}]`,
    model: (r) => (ctx.known.has(r.name) ? ctx.prefix + className(r.name) : 'Any'),
    enum: (r) => enumExpr(r, ctx),
    union: (_r, variants) => dedupe(variants).join(' | ') || 'Any',
    nullable: (_r, inner) => (inner.split(' | ').includes('None') ? inner : `${inner} | None`),
    literal: (r) => (r.value === null ? 'None' : `Literal[${JSON.stringify(r.value)}]`),
    map: (_r, value) => `dict[str, ${value}]`,
  });
}

/** True when the type needs `datetime` imported. */
export function needsDatetime(expr: string): boolean {
  return expr.includes('datetime.');
}

/** Whether a TypeRef ultimately is a JSON object model (used for body/response adapters). */
export function isModelRef(ref: TypeRef): ref is Extract<TypeRef, { kind: 'model' }> {
  return ref.kind === 'model';
}
