/**
 * IR `TypeRef` -> Python type annotation.
 *
 * The switch is exhaustive over every `kind` oagen defines and calls
 * `assertNever` in the default branch, so a future oagen release that adds a
 * kind breaks the build instead of emitting bad Python.
 */
import { assertNever, type TypeRef } from '@workos/oagen';

/** How model and enum names render in the module being generated (`Order`, `orders_v0.Order`). */
export interface TypeContext {
  model(name: string): string;
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
      // Compile error here if oagen adds a new TypeRef kind.
      return assertNever(ref);
  }
}

/** `X | None` unless the annotation already admits `None`. */
export function optional(annotation: string): string {
  return annotation.split(' | ').includes('None') ? annotation : `${annotation} | None`;
}

export function unwrap(ref: TypeRef): TypeRef {
  return ref.kind === 'nullable' ? unwrap(ref.inner) : ref;
}

/** oagen renders "no body" as the `unknown` primitive. */
export function isVoid(ref: TypeRef | undefined): boolean {
  if (!ref) return true;
  const r = unwrap(ref);
  return r.kind === 'primitive' && r.type === 'unknown';
}

/** Model and enum names referenced by a type (transitively through arrays, maps, unions). */
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

/** Import lines a rendered module needs for the annotations it contains. */
export function importsFor(source: string): string[] {
  const text = source.replace(/"""[\s\S]*?"""/g, ''); // docstrings do not count
  const lines: string[] = [];
  if (/\bdatetime\./.test(text)) lines.push('import datetime');
  const abc = ['AsyncIterator', 'Iterator', 'Mapping'].filter((n) => new RegExp(`\\b${n}\\b`).test(text));
  if (abc.length) lines.push(`from collections.abc import ${abc.join(', ')}`);
  const typing = ['Annotated', 'Any', 'Literal', 'TypeAlias'].filter((n) => new RegExp(`\\b${n}\\b`).test(text));
  if (typing.length) lines.push(`from typing import ${typing.join(', ')}`);
  return lines;
}
