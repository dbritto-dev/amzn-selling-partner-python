/**
 * Models and enums.
 *
 * pydantic v2 models, one package per API version: the spec build names
 * components `<package>:<Name>` (`orders_v0:Order`), so every package gets
 * `models/<package>/__init__.py` with all of its models (one module, so model
 * cross-references never form import cycles) and `models/<package>/enums.py`.
 * Names without a package (single-spec runs, enums oagen synthesises for
 * inline parameter enums) go to the package of the service that uses them, or
 * `shared` when several do.
 */
import type { ApiSpec, EmitterContext, Enum, GeneratedFile, Model, Operation, Service } from '@workos/oagen';
import { HEADER_DOC, className, docstring, fieldName, file, pyStr, snakeCase, Uniquer } from './naming.js';
import { importsFor, optional, referencedNames, renderTypeRef, type TypeContext } from './types.js';

export const SHARED = 'shared';

export interface Placement {
  pkg: string; // dotted package under models/: `orders_v0`, `notifications.order_change`
  cls: string; // python class name
}

export interface Packages {
  models: Map<string, Placement>;
  enums: Map<string, Placement>;
  /** Package of each service's own models (where its synthesised enums go). */
  servicePkg: Map<string, string>;
  /** Every package, sorted. */
  pkgs: string[];
  /** Python module path of a package: `notifications.order_change` -> `notifications/order_change`. */
  modulePath(pkg: string): string;
  /** Import alias of a package inside another module (`notifications_order_change`). */
  alias(pkg: string): string;
}

// -- package planning ----------------------------------------------------------------------

export function splitName(name: string): { pkg: string | null; base: string } {
  const i = name.indexOf(':');
  return i < 0 ? { pkg: null, base: name } : { pkg: name.slice(0, i), base: name.slice(i + 1) };
}

function opRefs(op: Operation, out: { models: Set<string>; enums: Set<string> }): void {
  for (const p of [...op.pathParams, ...op.queryParams, ...op.headerParams, ...(op.cookieParams ?? [])]) referencedNames(p.type, out);
  if (op.requestBody) referencedNames(op.requestBody, out);
  referencedNames(op.response, out);
  for (const r of op.successResponses ?? []) referencedNames(r.type, out);
  for (const e of op.errors) if (e.type) referencedNames(e.type, out);
}

/** Models and enums reachable from a service's operations (transitively through model fields). */
export function reachable(spec: ApiSpec, service: Service): { models: Set<string>; enums: Set<string> } {
  const byName = new Map(spec.models.map((m) => [m.name, m]));
  const out = { models: new Set<string>(), enums: new Set<string>() };
  for (const op of service.operations) opRefs(op, out);
  const queue = [...out.models];
  const seen = new Set<string>();
  while (queue.length) {
    const name = queue.pop()!;
    if (seen.has(name)) continue;
    seen.add(name);
    const model = byName.get(name);
    if (!model) continue;
    for (const f of model.fields) referencedNames(f.type, out);
    if (model.discriminator) for (const v of Object.values(model.discriminator.mapping)) out.models.add(v);
    for (const n of out.models) if (!seen.has(n)) queue.push(n);
  }
  return out;
}

export function planPackages(spec: ApiSpec): Packages {
  const servicePkg = new Map<string, string>();
  const owners = new Map<string, Set<string>>(); // unprefixed name -> packages of the services using it
  for (const service of spec.services) {
    const refs = reachable(spec, service);
    const counts = new Map<string, number>();
    for (const n of [...refs.models, ...refs.enums]) {
      const { pkg } = splitName(n);
      if (pkg) counts.set(pkg, (counts.get(pkg) ?? 0) + 1);
    }
    const best = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0];
    const pkg = best ? best[0] : snakeCase(service.name);
    servicePkg.set(service.name, pkg);
    for (const n of [...refs.models, ...refs.enums]) {
      if (splitName(n).pkg) continue;
      let set = owners.get(n);
      if (!set) owners.set(n, (set = new Set()));
      set.add(pkg);
    }
  }
  const pkgOf = (name: string): string => {
    const { pkg } = splitName(name);
    if (pkg) return pkg;
    const set = owners.get(name);
    return set && set.size === 1 ? [...set][0]! : SHARED;
  };
  const models = new Map<string, Placement>();
  const enums = new Map<string, Placement>();
  const used = new Map<string, Uniquer>();
  const take = (pkg: string, base: string): string => {
    let u = used.get(pkg);
    if (!u) used.set(pkg, (u = new Uniquer()));
    return u.take(className(base));
  };
  for (const m of [...spec.models].sort((a, b) => a.name.localeCompare(b.name))) {
    const pkg = pkgOf(m.name);
    models.set(m.name, { pkg, cls: take(pkg, splitName(m.name).base) });
  }
  for (const e of [...spec.enums].sort((a, b) => a.name.localeCompare(b.name))) {
    const pkg = pkgOf(e.name);
    enums.set(e.name, { pkg, cls: take(pkg, splitName(e.name).base) });
  }
  const pkgs = [...new Set([...models.values(), ...enums.values()].map((p) => p.pkg))].sort();
  return {
    models,
    enums,
    servicePkg,
    pkgs,
    modulePath: (pkg) => pkg.split('.').join('/'),
    alias: (pkg) => pkg.replace(/\./g, '_'),
  };
}

const plans = new WeakMap<ApiSpec, Packages>();

/** Package plan of the spec being generated (computed once per run). */
export function packagesOf(ctx: EmitterContext): Packages {
  let p = plans.get(ctx.spec);
  if (!p) plans.set(ctx.spec, (p = planPackages(ctx.spec)));
  return p;
}

/** `from ..models... import <pkg> [as alias]` from a module `depth` packages below `models/`. */
export function importPackage(pkg: string, packages: Packages, from: string): string {
  const parts = pkg.split('.');
  const last = parts.pop()!;
  const parent = parts.length ? `${from}.${parts.join('.')}` : from;
  const alias = packages.alias(pkg);
  return alias === last ? `from ${parent} import ${last}` : `from ${parent} import ${last} as ${alias}`;
}

// -- enums ---------------------------------------------------------------------------------

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
  const base = numeric ? 'int' : 'str';
  const lines = [`class ${cls}(${base}, Enum):`];
  const used = new Uniquer(['name', 'value', 'mro']);
  for (const v of values) {
    const name = memberName(v, used);
    // bandit B105 flags assignments whose target name looks like a credential; an enum value is a wire constant
    const nosec = /pas+wo?r?d|pass|pwd|token|secret/i.test(name) ? '  # nosec B105' : '';
    lines.push(`    ${name} = ${numeric ? String(v) : pyStr(String(v))}${nosec}`);
  }
  // Python 3.11+ returns "Name.MEMBER" from str() on a str-mixin enum, which
  // would leak into query strings. Force the value back.
  lines.push('', `    __str__ = ${base}.__str__`);
  return lines;
}

export function renderEnumsModule(pkg: string, enums: [Enum, string][]): string {
  const out: string[] = [];
  out.push(`"""Enums of ${pkg || 'the API'}.`, '', HEADER_DOC, '"""', '', 'from __future__ import annotations', '', 'from enum import Enum', '', '');
  for (const [e, cls] of enums) out.push(...renderEnum(e, cls), '', '');
  out.push('__all__ = [', ...enums.map(([, cls]) => cls).sort().map((n) => `    ${pyStr(n)},`), ']', '');
  return out.join('\n');
}

export function generateEnums(ctx: EmitterContext): GeneratedFile[] {
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

// -- models --------------------------------------------------------------------------------

const SYNTHETIC_ADDITIONAL = 'Additional properties not captured by named fields';

/** A model with no fields and a discriminator is a tagged union of its mapping targets. */
export function isDiscriminatedAlias(model: Model): boolean {
  return model.fields.length === 0 && model.discriminator !== undefined;
}

export function renderModel(model: Model, cls: string, ctx: TypeContext): string[] {
  const lines: string[] = [];
  if (isDiscriminatedAlias(model)) {
    const variants = [...new Set(Object.values(model.discriminator!.mapping))].map((v) => ctx.model(v));
    const expr = variants.join(' | ') || 'Any';
    if (variants.length > 1 && !variants.includes('Any')) {
      lines.push(`${cls}: TypeAlias = Annotated[${expr}, Field(discriminator=${pyStr(fieldName(model.discriminator!.property))})]`);
    } else {
      lines.push(`${cls}: TypeAlias = ${expr}`);
    }
    return lines;
  }
  lines.push(`class ${cls}(SpecModel):`);
  if (model.description) lines.push(...docstring(model.description, '    '), '');
  const used = new Uniquer(['model_config']);
  // pydantic (like dataclasses) needs the fields without defaults first
  const ordered = [...model.fields.filter((f) => f.required), ...model.fields.filter((f) => !f.required)];
  let count = 0;
  for (const f of ordered) {
    if (f.name === 'additionalProperties' && f.description === SYNTHETIC_ADDITIONAL) continue;
    const py = used.take(fieldName(f.domainName ?? f.name));
    const t = renderTypeRef(f.type, ctx);
    const aliased = py !== f.name;
    if (f.required) {
      lines.push(aliased ? `    ${py}: ${t} = Field(alias=${pyStr(f.name)})` : `    ${py}: ${t}`);
    } else {
      // an optional field can be non-nullable in the spec; it still carries a None default in Python
      lines.push(aliased ? `    ${py}: ${optional(t)} = Field(default=None, alias=${pyStr(f.name)})` : `    ${py}: ${optional(t)} = None`);
    }
    count++;
  }
  if (count === 0 && !model.description) lines.push('    pass');
  return lines;
}

/** Type context inside `models/<pkg>/__init__.py`: same-package classes by name, others through their package alias. */
function moduleContext(pkg: string, packages: Packages, foreign: Set<string>): TypeContext {
  const ref = (place: Placement | undefined): string => {
    if (!place) return 'Any';
    if (place.pkg === pkg) return place.cls;
    foreign.add(place.pkg);
    return `${packages.alias(place.pkg)}.${place.cls}`;
  };
  return { model: (name) => ref(packages.models.get(name)), enum: (name) => ref(packages.enums.get(name)) };
}

export function renderModelsModule(pkg: string, models: [Model, string][], enums: string[], packages: Packages, children: string[]): string {
  const foreign = new Set<string>();
  const ctx = moduleContext(pkg, packages, foreign);
  const body: string[] = [];
  for (const [m, cls] of models.filter(([m]) => !isDiscriminatedAlias(m))) body.push(...renderModel(m, cls, ctx), '', '');
  for (const [m, cls] of models.filter(([m]) => isDiscriminatedAlias(m))) body.push(...renderModel(m, cls, ctx));
  const text = body.join('\n');
  const out: string[] = [];
  out.push(`"""Models of ${pkg || 'the API'}.`, '', HEADER_DOC, '"""', '', 'from __future__ import annotations', '');
  out.push(...importsFor(text), '');
  if (text.includes('Field(')) out.push('from pydantic import Field', '');
  const depth = pkg ? pkg.split('.').length : 0;
  const up = '.'.repeat(depth + 1); // `models/` relative to this package
  if (models.some(([m]) => !isDiscriminatedAlias(m))) out.push(`from ${up}_base import SpecModel`);
  if (enums.length) out.push(`from .enums import ${[...enums].sort().join(', ')}`);
  for (const other of [...foreign].sort()) out.push(importPackage(other, packages, up.slice(0, -1) || '.'));
  if (children.length) out.push('', `#: subpackages: ${children.join(', ')}`);
  if (text) out.push('', '', text.trimEnd());
  out.push('', '', '__all__ = [', ...[...models.map(([, cls]) => cls), ...enums].sort().map((n) => `    ${pyStr(n)},`), ']', '');
  return out.join('\n');
}

export const BASE_MODULE = `"""Base class of every generated model.

${HEADER_DOC}
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel, ConfigDict, TypeAdapter

MODEL_CONFIG = ConfigDict(
    defer_build=True,
    extra="allow",
    populate_by_name=True,
    frozen=True,
    val_json_bytes="base64",
    ser_json_bytes="base64",
)

#: Config for TypeAdapters over non-model types (lists, unions, primitives).
ADAPTER_CONFIG = ConfigDict(
    populate_by_name=True,
    val_json_bytes="base64",
    ser_json_bytes="base64",
)


class SpecModel(BaseModel):
    """Frozen, alias-aware model; unknown wire fields are kept (\`\`extra="allow"\`\`).

    Attributes are snake_case, the wire names are aliases
    (\`\`Order(AmazonOrderId=...)\`\` and \`\`Order(amazon_order_id=...)\`\` both work),
    and the schema is built on first use (\`\`defer_build\`\`), so importing a
    models module only creates classes.
    """

    model_config = MODEL_CONFIG


def adapter_for(python_type: Any) -> TypeAdapter[Any]:
    """\`\`TypeAdapter\`\` for a response/body type (models carry their own config)."""
    if isinstance(python_type, type) and issubclass(python_type, BaseModel):
        return TypeAdapter(python_type)
    return TypeAdapter(cast(Any, python_type), config=ADAPTER_CONFIG)


__all__ = ["ADAPTER_CONFIG", "MODEL_CONFIG", "SpecModel", "adapter_for"]
`;

export function generateModels(ctx: EmitterContext): GeneratedFile[] {
  const spec = ctx.spec;
  const packages = packagesOf(ctx);
  const byPkg = new Map<string, { models: [Model, string][]; enums: string[]; children: Set<string> }>();
  const ensure = (pkg: string) => {
    let e = byPkg.get(pkg);
    if (!e) byPkg.set(pkg, (e = { models: [], enums: [], children: new Set() }));
    return e;
  };
  for (const m of spec.models) {
    const place = packages.models.get(m.name);
    if (place) ensure(place.pkg).models.push([m, place.cls]);
  }
  for (const place of packages.enums.values()) ensure(place.pkg).enums.push(place.cls);
  for (const pkg of packages.pkgs) {
    const parts = pkg.split('.');
    for (let i = parts.length - 1; i > 0; i--) ensure(parts.slice(0, i).join('.')).children.add(parts[i]!);
  }
  const files: GeneratedFile[] = [file('models/_base.py', BASE_MODULE)];
  for (const [pkg, e] of [...byPkg.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    e.models.sort((a, b) => a[1].localeCompare(b[1]));
    files.push(file(`models/${packages.modulePath(pkg)}/__init__.py`, renderModelsModule(pkg, e.models, e.enums, packages, [...e.children].sort())));
  }
  const top = [...new Set(packages.pkgs.map((p) => p.split('.')[0]!))].sort();
  files.push(file('models/__init__.py', `"""Models of ${spec.name}: one package per API version.\n\n${HEADER_DOC}\n\nPackages: ${top.join(', ')}.\n"""\n\nfrom __future__ import annotations\n`));
  return files;
}
