/**
 * Resources: one `resources/<service>.py` per service with a sync and an async
 * class, one method per operation. Method names come from
 * `ctx.resolvedOperations` (oagen's resolver + `operationHints`); each method
 * builds its parameters explicitly and calls the generated HTTP client.
 */
import { resolveOperations, type EmitterContext, type GeneratedFile, type Operation, type Parameter, type ResolvedOperation, type Service, type TypeRef } from '@workos/oagen';
import { HEADER_DOC } from './header.js';
import { docstring, fieldName, identifier, paramName, pyStr, snakeCase, Uniquer } from './naming.js';
import type { EmitterOptions } from './options.js';
import type { Packages } from './packages.js';
import { paginationFor, type PaginationDescriptor } from './pagination.js';
import { parseRateLimit } from './ratelimits.js';
import { isVoid, renderTypeRef, unwrap, type TypeContext } from './types.js';

interface ParamPlan {
  py: string;
  wire: string;
  required: boolean;
  location: 'path' | 'query' | 'header';
  annotation: string;
  /** Python expression producing the wire value from the parameter. */
  encode: string;
}

interface BodyPlan {
  required: boolean;
  annotation: string;
  /** keyword arguments of `request()` carrying the body */
  call: string;
}

interface OpPlan {
  op: Operation;
  name: string;
  params: ParamPlan[];
  pathExpr: string;
  body: BodyPlan | null;
  responseExpr: string; // python type expression or "None"
  responsesExpr: string | null; // {code: type, ...}
  returnType: string;
  errorExpr: string | null;
  rateLimit: { rate: number; burst: number } | null;
  pagination: (PaginationDescriptor & { items: string[]; token: string[]; itemType: string }) | null;
  doc: string;
}

function paramKind(ref: TypeRef): 'scalar' | 'array' | 'object' {
  const r = unwrap(ref);
  if (r.kind === 'array') return 'array';
  if (r.kind === 'map' || r.kind === 'model') return 'object';
  return 'scalar';
}

function annotate(p: Parameter, ctx: TypeContext): string {
  const t = renderTypeRef(p.type, ctx);
  // enum-typed parameters accept the enum member or its string value
  return unwrap(p.type).kind === 'enum' && !t.startsWith('Literal[') ? `${t} | str` : t;
}

function encodeQuery(py: string, p: Parameter): string {
  const kind = paramKind(p.type);
  if (kind === 'array') {
    const style = p.style ?? 'form';
    const explode = p.explode ?? true;
    if (style === 'form' && explode) return py; // repeated keys
    const sep = style === 'form' ? ',' : (style as string) === 'pipeDelimited' ? '|' : (style as string) === 'spaceDelimited' ? ' ' : ',';
    return `joined(${py}, ${pyStr(sep)})`;
  }
  return py;
}

function encodeHeader(py: string, p: Parameter): string {
  return paramKind(p.type) === 'array' ? `joined(${py})` : py;
}

function encodePath(py: string, p: Parameter, greedy: boolean): string {
  const inner = paramKind(p.type) === 'array' ? `joined(${py})` : py;
  return greedy ? `path_segment(${inner}, greedy=True)` : `path_segment(${inner})`;
}

function attrPath(wire: string): string[] {
  return wire.split('.').map((s) => fieldName(s));
}

function itemTypeOf(ctx: EmitterContext, op: Operation, desc: PaginationDescriptor, tctx: TypeContext): string {
  const spec = ctx.spec;
  let model = (() => {
    const r = unwrap(op.response);
    return r.kind === 'model' ? spec.models.find((m) => m.name === r.name) : undefined;
  })();
  let ref: TypeRef | undefined;
  for (const part of desc.itemsPath.split('.')) {
    if (!model) return 'Any';
    const field = model.fields.find((f) => f.name === part);
    if (!field) return 'Any';
    ref = field.type;
    const r = unwrap(field.type);
    model = r.kind === 'model' ? spec.models.find((m) => m.name === r.name) : undefined;
  }
  if (!ref) return 'Any';
  const r = unwrap(ref);
  if (desc.itemsIsObject) return renderTypeRef(r, tctx);
  if (r.kind === 'array') return renderTypeRef(r.items, tctx);
  return 'Any';
}

export function planOperation(ctx: EmitterContext, resolved: ResolvedOperation, name: string, pkg: string, tctx: TypeContext, opts: EmitterOptions, notes: string[]): OpPlan {
  const op = resolved.operation;
  const used = new Uniquer(['self', 'request_options', 'body', 'params', 'headers']);
  const params: ParamPlan[] = [];
  const greedy = new Set(opts.greedyPathParams);
  let pathExpr = op.path;
  let hasPathParams = false;
  for (const m of op.path.matchAll(/\{([^{}]+)\}/g)) {
    const wire = m[1]!;
    const p: Parameter = op.pathParams.find((x) => x.name === wire) ?? { name: wire, type: { kind: 'primitive', type: 'string' }, required: true };
    const py = used.take(paramName(wire));
    params.push({ py, wire, required: true, location: 'path', annotation: annotate(p, tctx), encode: encodePath(py, p, greedy.has(wire)) });
    pathExpr = pathExpr.replace(`{${wire}}`, `{${encodePath(py, p, greedy.has(wire))}}`);
    hasPathParams = true;
  }
  pathExpr = hasPathParams ? `f${pyStr(pathExpr).replace(/\\"/g, '"')}` : pyStr(op.path);
  for (const p of op.queryParams) {
    const py = used.take(paramName(p.name));
    params.push({ py, wire: p.name, required: p.required, location: 'query', annotation: annotate(p, tctx), encode: encodeQuery(py, p) });
  }
  for (const p of op.headerParams) {
    const py = used.take(paramName(p.name));
    params.push({ py, wire: p.name, required: p.required, location: 'header', annotation: annotate(p, tctx), encode: encodeHeader(py, p) });
  }
  if (op.cookieParams?.length) notes.push(`${pkg}.${op.name}: cookie parameters are not supported and are ignored`);
  let body: BodyPlan | null = null;
  if (op.requestBody) {
    const enc = op.requestBodyEncoding ?? 'json';
    const t = renderTypeRef(op.requestBody, tctx);
    const isModel = unwrap(op.requestBody).kind === 'model';
    if (enc === 'json') body = { required: true, annotation: isModel ? `${t} | Mapping[str, Any]` : t, call: 'json=body' };
    else if (enc === 'form-data') body = { required: true, annotation: 'Mapping[str, Any]', call: 'files=body' };
    else if (enc === 'form-urlencoded') body = { required: true, annotation: 'Mapping[str, Any]', call: 'data=body' };
    else if (enc === 'text') body = { required: true, annotation: 'str', call: 'content=body, content_type="text/plain"' };
    else body = { required: true, annotation: 'bytes', call: 'content=body' };
  }
  // responses
  const typeExpr = (ref: TypeRef): string => (isVoid(ref) ? 'None' : renderTypeRef(ref, tctx));
  let responseExpr = typeExpr(op.response);
  let responsesExpr: string | null = null;
  let returnType = responseExpr;
  if (op.successResponses && op.successResponses.length > 1) {
    const entries = op.successResponses.map((r) => `${r.statusCode}: ${typeExpr(r.type)}`);
    responsesExpr = `{${entries.join(', ')}}`;
    const types = [...new Set(op.successResponses.map((r) => typeExpr(r.type)))];
    returnType = types.join(' | ');
    const first = op.successResponses.find((r) => !isVoid(r.type));
    responseExpr = first ? typeExpr(first.type) : 'None';
  }
  const errors = op.errors.filter((e) => e.type && !isVoid(e.type));
  const err = errors.find((e) => e.statusCode === 400) ?? errors[0];
  const errorExpr = err?.type ? renderTypeRef(err.type, tctx) : null;
  const rateLimit = parseRateLimit(op.description);
  if (!rateLimit) notes.push(`rate limit: ${pkg}.${op.name}: no usage-plan table in the description`);
  const log: { key: string; message: string }[] = [];
  const desc = paginationFor(ctx.spec, op, pkg, log);
  for (const l of log) notes.push(`pagination: ${l.key}: ${l.message}`);
  let pagination: OpPlan['pagination'] = null;
  if (desc) {
    const tokenParam = params.find((p) => p.location !== 'path' && p.wire === desc.nextTokenParam);
    if (!tokenParam) notes.push(`pagination: ${pkg}.${op.name}: token parameter ${desc.nextTokenParam} not found; skipped`);
    else pagination = { ...desc, nextTokenParam: tokenParam.py, items: attrPath(desc.itemsPath), token: attrPath(desc.nextTokenPath), itemType: itemTypeOf(ctx, op, desc, tctx) };
  }
  const docParts: string[] = [];
  if (op.description) docParts.push(op.description.trim());
  if (op.deprecated) docParts.push('Deprecated.');
  docParts.push(`${op.httpMethod.toUpperCase()} ${op.path}`);
  return { op, name, params, pathExpr, body, responseExpr, responsesExpr, returnType, errorExpr, rateLimit, pagination, doc: docParts.join('\n\n') };
}

function signature(plan: OpPlan, isAsync: boolean, name: string, ret: string): string[] {
  const parts: string[] = ['self', '*'];
  const required = plan.params.filter((p) => p.required);
  const optional = plan.params.filter((p) => !p.required);
  for (const p of required) parts.push(`${p.py}: ${p.annotation}`);
  if (plan.body?.required) parts.push(`body: ${plan.body.annotation}`);
  for (const p of optional) parts.push(`${p.py}: ${p.annotation} | None = None`);
  if (plan.body && !plan.body.required) parts.push(`body: ${plan.body.annotation} | None = None`);
  parts.push('request_options: RequestOptions | None = None');
  const def = isAsync ? 'async def' : 'def';
  return [`    ${def} ${name}(`, ...parts.map((p) => `        ${p},`), `    ) -> ${ret}:`];
}

function renderMethod(plan: OpPlan, isAsync: boolean, service: string): string[] {
  const lines: string[] = [];
  lines.push(...signature(plan, isAsync, plan.name, plan.returnType));
  lines.push(...docstring(plan.doc, '        '));
  const query = plan.params.filter((p) => p.location === 'query');
  const headers = plan.params.filter((p) => p.location === 'header');
  const args: string[] = [pyStr(plan.op.httpMethod.toUpperCase()), plan.pathExpr, `operation=${pyStr(plan.op.name)}`, `service=SERVICE`];
  if (query.length) {
    lines.push(`        params: dict[str, Any] = {${query.map((p) => `${pyStr(p.wire)}: ${p.encode}`).join(', ')}}`);
    args.push('params=params');
  }
  if (headers.length) {
    lines.push(`        headers: dict[str, Any] = {${headers.map((p) => `${pyStr(p.wire)}: ${p.encode}`).join(', ')}}`);
    args.push('headers=headers');
  }
  if (plan.body) args.push(plan.body.call);
  if (plan.responseExpr !== 'None') args.push(`response=${plan.responseExpr}`);
  if (plan.responsesExpr) args.push(`responses=${plan.responsesExpr}`);
  if (plan.errorExpr) args.push(`error=${plan.errorExpr}`);
  if (plan.rateLimit) args.push(`rate_limit=RateLimit(${plan.rateLimit.rate}, ${plan.rateLimit.burst})`);
  args.push('options=request_options');
  lines.push(`        return ${isAsync ? 'await ' : ''}self._client.request(`);
  for (const a of args) lines.push(`            ${a},`);
  lines.push('        )');
  void service;
  return lines;
}

function renderIterMethod(plan: OpPlan, isAsync: boolean): string[] {
  const pg = plan.pagination!;
  const ret = `${isAsync ? 'AsyncIterator' : 'Iterator'}[${pg.itemType}]`;
  const lines: string[] = [];
  lines.push(...signature(plan, false, `iter_${plan.name}`, ret));
  const what = pg.itemsIsObject ? `the \`\`${pg.itemsPath}\`\` object of every page` : `every item of \`\`${pg.itemsPath}\`\` across pages`;
  lines.push(...docstring(`${what} of \`\`${plan.name}\`\`, following \`\`${pg.nextTokenPath}\`\` -> \`\`${pg.nextTokenParam}\`\`.`, '        '));
  const kwargs = [...plan.params.map((p) => `${pyStr(p.py)}: ${p.py}`), ...(plan.body ? ['"body": body'] : []), '"request_options": request_options'];
  const tuple = (xs: string[]) => `(${xs.map(pyStr).join(', ')}${xs.length === 1 ? ',' : ''})`;
  const args = [
    `self.${plan.name}`,
    `{${kwargs.join(', ')}}`,
    `items=${tuple(pg.items)}`,
    `token=${tuple(pg.token)}`,
    `token_param=${pyStr(pg.nextTokenParam)}`,
    `wire_items=${tuple(pg.itemsPath.split('.'))}`,
    `wire_token=${tuple(pg.nextTokenPath.split('.'))}`,
  ];
  if (pg.dropParamsOnNext) args.push('drop_params_on_next=True');
  if (pg.keepParams?.length) args.push(`keep_params=${tuple(pg.keepParams.map((k) => paramName(k)))}`);
  if (pg.itemsIsObject) args.push('single=True');
  lines.push(`        return ${isAsync ? 'apaginate' : 'paginate'}(`);
  for (const a of args) lines.push(`            ${a},`);
  lines.push('        )');
  return lines;
}

export function renderResourceModule(ctx: EmitterContext, service: Service, plans: OpPlan[], module: string, imports: string[], packages: Packages): string {
  const cls = `${service.name}Client`;
  const body: string[] = [];
  for (const isAsync of [false, true]) {
    body.push('', `class ${isAsync ? 'Async' : ''}${cls}:`);
    body.push(`    """${isAsync ? 'Asynchronous' : 'Synchronous'} \`\`${service.name}\`\` resource${service.description ? `: ${service.description.trim().split('\n')[0]}` : ''}."""`);
    body.push('', '    __slots__ = ("_client",)', '', `    def __init__(self, client: ${isAsync ? 'AsyncHttpClient' : 'HttpClient'}) -> None:`, '        self._client = client');
    for (const plan of plans) {
      body.push('', ...renderMethod(plan, isAsync, module));
      if (plan.pagination) body.push('', ...renderIterMethod(plan, isAsync));
    }
    body.push('');
  }
  const text = body.join('\n');
  const out: string[] = [];
  out.push(`"""\`\`${service.name}\`\` resource of ${ctx.spec.name}.`, '', HEADER_DOC, '"""', '', 'from __future__ import annotations', '');
  if (text.includes('datetime.')) out.push('import datetime');
  const abc = ['AsyncIterator', 'Iterator', 'Mapping'].filter((n) => new RegExp(`\\b${n}\\b`).test(text));
  if (abc.length) out.push(`from collections.abc import ${abc.join(', ')}`);
  const typing = ['Any', 'Literal'].filter((n) => new RegExp(`\\b${n}\\b`).test(text));
  if (typing.length) out.push(`from typing import ${typing.join(', ')}`);
  out.push('');
  const helpers = ['AsyncHttpClient', 'HttpClient', 'RateLimit', 'RequestOptions', 'apaginate', 'joined', 'paginate', 'path_segment'].filter((n) =>
    new RegExp(`\\b${n}\\b`).test(text),
  );
  out.push(`from ..http_client import ${helpers.join(', ')}`);
  out.push(...imports);
  out.push('', `SERVICE = ${pyStr(module)}`, '');
  out.push(text.trimEnd(), '', '', `__all__ = [${pyStr('Async' + cls)}, ${pyStr(cls)}]`, '');
  void packages;
  return out.join('\n');
}

export interface ResourceIndex {
  module: string;
  service: string;
  cls: string;
  operations: { operationId: string; method: string; httpMethod: string; path: string; paginated: boolean; rateLimit: boolean }[];
}

/** Resource groups: resolved operations by mount target (`mountRules` / `operationHints.mountOn` may merge or move services). */
export function resourceGroups(ctx: EmitterContext): { service: Service; ops: ResolvedOperation[] }[] {
  const resolved = ctx.resolvedOperations ?? resolveOperations(ctx.spec);
  const byTarget = new Map<string, ResolvedOperation[]>();
  for (const r of resolved) {
    if (r.urlBuilder) continue;
    let list = byTarget.get(r.mountOn);
    if (!list) byTarget.set(r.mountOn, (list = []));
    list.push(r);
  }
  const groups: { service: Service; ops: ResolvedOperation[] }[] = [];
  for (const [name, ops] of byTarget) {
    const original = ctx.spec.services.find((s) => s.name === name);
    const description = original?.description ?? ops.map((o) => o.service.description).find((d) => d);
    groups.push({ service: { name, description, operations: ops.map((o) => o.operation) }, ops });
  }
  return groups;
}

/** Resource module name of a mount target: the models package of the services mounted there. */
export function resourceModuleOf(name: string, ops: ResolvedOperation[], packages: Packages): string {
  const pkg = packages.servicePkg.get(name) ?? ops.map((o) => packages.servicePkg.get(o.service.name)).find((p) => p) ?? snakeCase(name);
  return identifier(pkg.replace(/\./g, '_'));
}

export function generateResources(_services: Service[], ctx: EmitterContext, packages: Packages, opts: EmitterOptions, notes: string[] = []): GeneratedFile[] {
  const files: GeneratedFile[] = [];
  const index: ResourceIndex[] = [];
  const modules = new Uniquer();
  for (const { service, ops } of resourceGroups(ctx)) {
    if (ops.length === 0) continue;
    const module = modules.take(resourceModuleOf(service.name, ops, packages));
    const pkg = packages.servicePkg.get(service.name) ?? module;
    const usedPkgs = new Set<string>();
    const tctx: TypeContext = {
      model: (name) => {
        const place = packages.models.get(name);
        if (!place) return 'Any';
        usedPkgs.add(place.pkg);
        return `${packages.alias(place.pkg)}.${place.cls}`;
      },
      enum: (name) => {
        const place = packages.enums.get(name);
        if (!place) return 'str';
        usedPkgs.add(place.pkg);
        return `${packages.alias(place.pkg)}.${place.cls}`;
      },
    };
    const names = new Uniquer();
    const plans: OpPlan[] = [];
    for (const r of ops) {
      let name = identifier(r.methodName);
      if (names.has(name)) {
        notes.push(`${module}: method name ${name} collides (${r.operation.httpMethod.toUpperCase()} ${r.operation.path}); add an operationHint`);
        name = names.take(name);
      } else names.take(name);
      plans.push(planOperation(ctx, r, name, pkg, tctx, opts, notes));
    }
    const imports = [...usedPkgs].sort().map((p) => importLine(p, packages));
    files.push({ path: `resources/${module}.py`, content: renderResourceModule(ctx, service, plans, module, imports, packages) });
    index.push({
      module,
      service: service.name,
      cls: `${service.name}Client`,
      operations: plans.map((p) => ({ operationId: p.op.name, method: p.name, httpMethod: p.op.httpMethod.toUpperCase(), path: p.op.path, paginated: p.pagination !== null, rateLimit: p.rateLimit !== null })),
    });
  }
  files.push({ path: 'resources/__init__.py', content: renderResourcesInit(ctx, index) });
  return files;
}

function importLine(pkg: string, packages: Packages): string {
  const alias = packages.alias(pkg);
  const parts = pkg.split('.');
  const last = parts.pop()!;
  const parent = parts.length ? `..models.${parts.join('.')}` : '..models';
  return alias === last ? `from ${parent} import ${last}` : `from ${parent} import ${last} as ${alias}`;
}

function renderResourcesInit(ctx: EmitterContext, index: ResourceIndex[]): string {
  const out: string[] = [];
  out.push(`"""Resources of ${ctx.spec.name}: one module per service, importable on demand.`, '', HEADER_DOC, '"""', '', 'from __future__ import annotations', '');
  out.push('#: resource module -> (sync class, async class)');
  out.push('SERVICES: dict[str, tuple[str, str]] = {');
  for (const s of index) out.push(`    ${pyStr(s.module)}: (${pyStr(s.cls)}, ${pyStr('Async' + s.cls)}),`);
  out.push('}', '');
  out.push('#: "<resource module>.<operationId>" -> (method name, HTTP method, path, paginated, has rate limit)');
  out.push('OPERATIONS: dict[str, tuple[str, str, str, bool, bool]] = {');
  const keys = new Uniquer();
  for (const s of index) {
    for (const o of s.operations) {
      const base = `${s.module}.${o.operationId}`;
      const key = keys.has(base) ? `${base}:${o.httpMethod}` : base; // duplicate operationIds (two methods on one path)
      keys.take(key);
      out.push(`    ${pyStr(key)}: (${pyStr(o.method)}, ${pyStr(o.httpMethod)}, ${pyStr(o.path)}, ${o.paginated ? 'True' : 'False'}, ${o.rateLimit ? 'True' : 'False'}),`);
    }
  }
  out.push('}', '', '__all__ = ["OPERATIONS", "SERVICES"]', '');
  return out.join('\n');
}
