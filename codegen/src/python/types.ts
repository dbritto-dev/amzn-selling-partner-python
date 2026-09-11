/** IR `TypeRef` -> Python type expression, exhaustive over every kind (the build breaks when oagen adds one). */
import { assertNever, type TypeRef } from '@workos/oagen';

export interface TypeContext {
  /** Python expression for a model (`Order`, `orders_v0.Order`). */
  model(name: string): string;
  /** Python expression for a named enum. */
  enum(name: string): string;
}

export function renderPrimitive(type: string, format?: string): string {
  if (type === 'string') {
    if (format === 'date-time' || format === 'dateTime') return 'datetime.datetime';
    if (format === 'date') return 'datetime.date';
    if (format === 'byte' || format === 'binary') return 'bytes';
    return 'str';
  }
  if (type === 'integer') return 'int';
  if (type === 'number') return 'float';
  if (type === 'boolean') return 'bool';
  return 'Any';
}

export function renderTypeRef(ref: TypeRef, ctx: TypeContext): string {
  switch (ref.kind) {
    case 'primitive':
      return renderPrimitive(ref.type, ref.format);
    case 'array':
      return `list[${renderTypeRef(ref.items, ctx)}]`;
    case 'nullable': {
      const inner = renderTypeRef(ref.inner, ctx);
      return inner.split(' | ').includes('None') ? inner : `${inner} | None`;
    }
    case 'model':
      return ctx.model(ref.name);
    case 'enum':
      return ctx.enum(ref.name);
    case 'union': {
      const parts = [...new Set(ref.variants.map((v) => renderTypeRef(v, ctx)))];
      return parts.join(' | ') || 'Any';
    }
    case 'map':
      return `dict[str, ${renderTypeRef(ref.valueType, ctx)}]`;
    case 'literal':
      return ref.value === null ? 'None' : `Literal[${JSON.stringify(ref.value)}]`;
    default:
      return assertNever(ref);
  }
}

export function unwrap(ref: TypeRef): TypeRef {
  return ref.kind === 'nullable' ? unwrap(ref.inner) : ref;
}

export function isVoid(ref: TypeRef | undefined): boolean {
  if (!ref) return true;
  const r = unwrap(ref);
  return r.kind === 'primitive' && r.type === 'unknown';
}

/** Model and enum names referenced by a type. */
export function referencedNames(ref: TypeRef, out: { models: Set<string>; enums: Set<string> }): void {
  switch (ref.kind) {
    case 'primitive':
    case 'literal':
      return;
    case 'array':
      referencedNames(ref.items, out);
      return;
    case 'nullable':
      referencedNames(ref.inner, out);
      return;
    case 'model':
      out.models.add(ref.name);
      return;
    case 'enum':
      out.enums.add(ref.name);
      return;
    case 'union':
      for (const v of ref.variants) referencedNames(v, out);
      return;
    case 'map':
      referencedNames(ref.valueType, out);
      return;
    default:
      return assertNever(ref);
  }
}
