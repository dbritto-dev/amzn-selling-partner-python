/**
 * Where every model and enum lives. The spec build names components
 * `<package>:<Name>` (`orders_v0:Order`), so a merged multi-API document keeps
 * one models package per API version. Names without a package (single-spec
 * runs, enums oagen synthesises for inline parameter enums) go to the package
 * of the service that uses them, or `shared` when several do.
 */
import type { ApiSpec, EmitterContext, Enum, Model, Operation, Service } from '@workos/oagen';
import { className, snakeCase, Uniquer } from './naming.js';
import { referencedNames } from './types.js';

export const SHARED = 'shared';

export interface Placement {
  pkg: string; // dotted package under models/, e.g. `orders_v0`, `notifications.order_change`
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
  /** Import alias of a package inside a resource module. */
  alias(pkg: string): string;
}

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
  while (queue.length) {
    const name = queue.pop()!;
    const model = byName.get(name);
    if (!model) continue;
    const before = out.models.size;
    for (const f of model.fields) referencedNames(f.type, out);
    if (model.discriminator) for (const v of Object.values(model.discriminator.mapping)) out.models.add(v);
    if (out.models.size > before) for (const n of out.models) if (!byName.has(n) || !queue.includes(n)) queue.push(n);
  }
  return out;
}

export function planPackages(spec: ApiSpec): Packages {
  const servicePkg = new Map<string, string>();
  const owners = new Map<string, Set<string>>(); // unprefixed name -> service packages using it
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
    if (set && set.size === 1) return [...set][0]!;
    return SHARED;
  };
  const models = new Map<string, Placement>();
  const enums = new Map<string, Placement>();
  const used = new Map<string, Uniquer>();
  const take = (pkg: string, base: string): string => {
    let u = used.get(pkg);
    if (!u) used.set(pkg, (u = new Uniquer()));
    return u.take(className(base));
  };
  const sortedModels = [...spec.models].sort((a: Model, b: Model) => a.name.localeCompare(b.name));
  const sortedEnums = [...spec.enums].sort((a: Enum, b: Enum) => a.name.localeCompare(b.name));
  for (const m of sortedModels) {
    const pkg = pkgOf(m.name);
    models.set(m.name, { pkg, cls: take(pkg, splitName(m.name).base) });
  }
  for (const e of sortedEnums) {
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

/** `from ..models... import ...` line that binds `alias(pkg)` in a resource module. */
export function importPackage(pkg: string, alias: string): string {
  const parts = pkg.split('.');
  const last = parts.pop()!;
  const parent = parts.length ? `..models.${parts.join('.')}` : '..models';
  return alias === last ? `from ${parent} import ${last}` : `from ${parent} import ${last} as ${alias}`;
}

const plans = new WeakMap<ApiSpec, Packages>();

/** Package plan of the spec being generated (computed once per run). */
export function packagesOf(ctx: EmitterContext): Packages {
  let p = plans.get(ctx.spec);
  if (!p) plans.set(ctx.spec, (p = planPackages(ctx.spec)));
  return p;
}
