/** Enums: one `models/<package>/enums.py` per package, `class Name(str, Enum)` as in the oagen tutorial. */
import type { Enum, EmitterContext, GeneratedFile } from '@workos/oagen';
import { HEADER_DOC, file } from './header.js';
import { pyStr, snakeCase, Uniquer } from './naming.js';
import { packagesOf } from './packages.js';

function memberName(value: string | number, used: Uniquer): string {
  let s = snakeCase(String(value)).toUpperCase();
  if (!s || /^[0-9]/.test(s)) s = `V_${s}`;
  if (s === 'FIELD') s = `V_${s}`;
  if (s === 'I' || s === 'O' || s === 'L') s = `${s}_`; // ruff E741 (ambiguous single letters)
  return used.take(s);
}

export function renderEnum(e: Enum, cls: string): string[] {
  const values = e.values.map((v) => v.value);
  const numeric = values.length > 0 && values.every((v) => typeof v === 'number');
  const lines = [`class ${cls}(${numeric ? 'int' : 'str'}, Enum):`];
  const used = new Uniquer(['name', 'value', 'mro']);
  if (values.length === 0) lines.push('    pass');
  for (const v of values) {
    const literal = numeric ? String(v) : pyStr(String(v));
    lines.push(`    ${memberName(v, used)} = ${literal}`);
  }
  return lines;
}

export function renderEnumsModule(pkg: string, enums: [Enum, string][]): string {
  const out: string[] = [];
  out.push(`"""Enums of ${pkg || 'the API'}.`, '', HEADER_DOC, '"""', '', 'from __future__ import annotations', '', 'from enum import Enum', '', '');
  const names: string[] = [];
  for (const [e, cls] of enums) {
    out.push(...renderEnum(e, cls), '', '');
    names.push(cls);
  }
  out.push('__all__ = [', ...names.sort().map((n) => `    ${pyStr(n)},`), ']', '');
  return out.join('\n');
}

export function generateEnums(_enums: Enum[], ctx: EmitterContext): GeneratedFile[] {
  const packages = packagesOf(ctx);
  const byPkg = new Map<string, [Enum, string][]>();
  for (const e of ctx.spec.enums) {
    const place = packages.enums.get(e.name);
    if (!place) continue;
    let list = byPkg.get(place.pkg);
    if (!list) byPkg.set(place.pkg, (list = []));
    list.push([e, place.cls]);
  }
  const files: GeneratedFile[] = [];
  for (const [pkg, list] of [...byPkg.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    list.sort((a, b) => a[1].localeCompare(b[1]));
    files.push(file(`models/${packages.modulePath(pkg)}/enums.py`, renderEnumsModule(pkg, list)));
  }
  return files;
}
