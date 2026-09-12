/**
 * Resources: one `resources/<package>.py` per service with a sync and an async
 * class, one method per operation.
 *
 * Method names come from `ctx.resolvedOperations` (oagen's resolver plus the
 * `operationHints` of the policy). Every method builds its parameters
 * explicitly and calls the generated HTTP client (`_http.py`), which encodes,
 * sends with retries and throttling, and decodes the response into the model
 * the method names. Operations with a page token also get an `iter_<method>`
 * generator.
 */
import { mergeSdkBehavior, resolveOperations, type DeepPartial, type EmitterContext, type GeneratedFile, type Operation, type Parameter, type ResolvedOperation, type SdkBehavior, type Service, type TypeRef } from '@workos/oagen';
import { HEADER_DOC, docstring, fieldName, file, identifier, paramName, pyStr, snakeCase, Uniquer } from './naming.js';
import { importPackage, packagesOf, type Packages } from './models.js';
import { paginationFor, type PaginationDescriptor } from './pagination.js';
import { parseRateLimit } from './ratelimits.js';
import { importsFor, isVoid, optional, renderTypeRef, unwrap, type TypeContext } from './types.js';

// -- emitter options (`emitterOptions.python` in oagen.config.ts) --------------------------

export interface EmitterOptions {
  /** Response header carrying the server's request id (surfaced on errors). */
  requestIdHeader: string;
  /** Response header carrying a rate hint after a 429 (requests per second). */
  rateHintHeader?: string;
  /** Path parameters that may contain `/` (not percent-encoded). */
  greedyPathParams: string[];
  /** Distribution name of the generated SDK, used in the User-Agent. */
  distribution: string;
  /** Extra client attributes: alias -> api or resource module (`invoices` -> `invoices_api_model`). */
  serviceAliases: Record<string, string>;
  /** Retry/timeout/error policy: `ctx.spec.sdk`, or oagen's defaults merged with `sdkBehavior` when the config carries one. */
  sdk: SdkBehavior;
}

export function optionsOf(ctx: EmitterContext): EmitterOptions {
  const raw = (ctx.emitterOptions ?? {}) as Partial<Omit<EmitterOptions, 'sdk'>> & { sdkBehavior?: DeepPartial<SdkBehavior> };
  return {
    sdk: raw.sdkBehavior ? mergeSdkBehavior(raw.sdkBehavior) : ctx.spec.sdk,
    requestIdHeader: raw.requestIdHeader ?? 'x-request-id',
    rateHintHeader: raw.rateHintHeader,
    greedyPathParams: raw.greedyPathParams ?? [],
    distribution: raw.distribution ?? ctx.namespace,
    serviceAliases: raw.serviceAliases ?? {},
  };
}

// -- operation planning --------------------------------------------------------------------

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
  annotation: string;
  /** keyword argument of `request()` carrying the body */
  call: string;
}

export interface OpPlan {
  op: Operation;
  name: string;
  params: ParamPlan[];
  pathExpr: string;
  body: BodyPlan | null;
  responseExpr: string; // python type expression or "None"
  responsesExpr: string | null; // {status: type, ...} when the operation has several success responses
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
  if (paramKind(p.type) !== 'array') return py;
  const style = p.style ?? 'form';
  const explode = p.explode ?? true;
  if (style === 'form' && explode) return py; // repeated keys
  const sep = (style as string) === 'pipeDelimited' ? '|' : (style as string) === 'spaceDelimited' ? ' ' : ',';
  return `joined(${py}, ${pyStr(sep)})`;
}

function encodePath(py: string, p: Parameter, greedy: boolean): string {
  const inner = paramKind(p.type) === 'array' ? `joined(${py})` : py;
  return greedy ? `path_segment(${inner}, greedy=True)` : `path_segment(${inner})`;
}

function itemTypeOf(ctx: EmitterContext, op: Operation, desc: PaginationDescriptor, tctx: TypeContext): string {
  const spec = ctx.spec;
  const r0 = unwrap(op.response);
  let model = r0.kind === 'model' ? spec.models.find((m) => m.name === r0.name) : undefined;
  let ref: TypeRef | undefined;
  for (const part of desc.itemsPath.split('.')) {
    const field = model?.fields.find((f) => f.name === part);
    if (!field) return 'Any';
    ref = field.type;
    const r = unwrap(field.type);
    model = r.kind === 'model' ? spec.models.find((m) => m.name === r.name) : undefined;
  }
  if (!ref) return 'Any';
  const r = unwrap(ref);
  if (desc.itemsIsObject) return renderTypeRef(r, tctx);
  return r.kind === 'array' ? renderTypeRef(r.items, tctx) : 'Any';
}

export function planOperation(ctx: EmitterContext, resolved: ResolvedOperation, name: string, pkg: string, tctx: TypeContext, opts: EmitterOptions, notes: string[]): OpPlan {
  const op = resolved.operation;
  const used = new Uniquer(['self', 'request_options', 'body', 'params', 'headers']);
  const params: ParamPlan[] = [];
  const greedy = new Set(opts.greedyPathParams);
  let pathExpr = op.path;
  for (const m of op.path.matchAll(/\{([^{}]+)\}/g)) {
    const wire = m[1]!;
    const p: Parameter = op.pathParams.find((x) => x.name === wire) ?? { name: wire, type: { kind: 'primitive', type: 'string' }, required: true };
    const py = used.take(paramName(wire));
    const encode = encodePath(py, p, greedy.has(wire));
    params.push({ py, wire, required: true, location: 'path', annotation: annotate(p, tctx), encode });
    pathExpr = pathExpr.replace(`{${wire}}`, `{${encode}}`);
  }
  pathExpr = params.length ? `f${pyStr(pathExpr).replace(/\\"/g, '"')}` : pyStr(op.path);
  for (const p of op.queryParams) {
    const py = used.take(paramName(p.name));
    params.push({ py, wire: p.name, required: p.required, location: 'query', annotation: annotate(p, tctx), encode: encodeQuery(py, p) });
  }
  for (const p of op.headerParams) {
    const py = used.take(paramName(p.name));
    params.push({ py, wire: p.name, required: p.required, location: 'header', annotation: annotate(p, tctx), encode: paramKind(p.type) === 'array' ? `joined(${py})` : py });
  }
  if (op.cookieParams?.length) notes.push(`${pkg}.${op.name}: cookie parameters are not supported and are ignored`);

  let body: BodyPlan | null = null;
  if (op.requestBody) {
    const t = renderTypeRef(op.requestBody, tctx);
    const isModel = unwrap(op.requestBody).kind === 'model';
    switch (op.requestBodyEncoding ?? 'json') {
      case 'json':
        body = { annotation: isModel ? `${t} | Mapping[str, Any]` : t, call: 'json=body' };
        break;
      case 'form-data':
        body = { annotation: 'Mapping[str, Any]', call: 'files=body' };
        break;
      case 'form-urlencoded':
        body = { annotation: 'Mapping[str, Any]', call: 'data=body' };
        break;
      case 'text':
        body = { annotation: 'str', call: 'content=body, content_type="text/plain"' };
        break;
      case 'binary':
        body = { annotation: 'bytes', call: 'content=body' };
        break;
    }
  }

  const typeExpr = (ref: TypeRef): string => (isVoid(ref) ? 'None' : renderTypeRef(ref, tctx));
  let responseExpr = typeExpr(op.response);
  let responsesExpr: string | null = null;
  let returnType = responseExpr;
  if (op.successResponses && op.successResponses.length > 1) {
    responsesExpr = `{${op.successResponses.map((r) => `${r.statusCode}: ${typeExpr(r.type)}`).join(', ')}}`;
    returnType = [...new Set(op.successResponses.map((r) => typeExpr(r.type)))].join(' | ');
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
    else pagination = { ...desc, nextTokenParam: tokenParam.py, items: desc.itemsPath.split('.').map(fieldName), token: desc.nextTokenPath.split('.').map(fieldName), itemType: itemTypeOf(ctx, op, desc, tctx) };
  }

  const doc: string[] = [];
  if (op.description) doc.push(op.description.trim());
  if (op.deprecated) doc.push('Deprecated.');
  doc.push(`${op.httpMethod.toUpperCase()} ${op.path}`);
  return { op, name, params, pathExpr, body, responseExpr, responsesExpr, returnType, errorExpr, rateLimit, pagination, doc: doc.join('\n\n') };
}

// -- rendering -----------------------------------------------------------------------------

/** `self, <path params>, <body>, <required params>, *, <optional params> = None, request_options = None`. */
function signature(plan: OpPlan, isAsync: boolean, name: string, ret: string): string[] {
  const parts: string[] = ['self'];
  for (const p of plan.params.filter((p) => p.location === 'path')) parts.push(`${p.py}: ${p.annotation}`);
  if (plan.body) parts.push(`body: ${plan.body.annotation}`);
  for (const p of plan.params.filter((p) => p.location !== 'path' && p.required)) parts.push(`${p.py}: ${p.annotation}`);
  parts.push('*');
  for (const p of plan.params.filter((p) => !p.required)) parts.push(`${p.py}: ${optional(p.annotation)} = None`);
  parts.push('request_options: RequestOptions | None = None');
  return [`    ${isAsync ? 'async def' : 'def'} ${name}(`, ...parts.map((p) => `        ${p},`), `    ) -> ${ret}:`];
}

function renderMethod(plan: OpPlan, isAsync: boolean): string[] {
  const lines = signature(plan, isAsync, plan.name, plan.returnType);
  lines.push(...docstring(plan.doc, '        '));
  const query = plan.params.filter((p) => p.location === 'query');
  const headers = plan.params.filter((p) => p.location === 'header');
  const args: string[] = [pyStr(plan.op.httpMethod.toUpperCase()), plan.pathExpr, `operation=${pyStr(plan.op.name)}`, 'service=SERVICE'];
  if (query.length) {
    // None values never reach the wire (the HTTP client drops them)
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
  lines.push(`        return ${isAsync ? 'await ' : ''}self._http.request(`, ...args.map((a) => `            ${a},`), '        )');
  return lines;
}

function renderIterMethod(plan: OpPlan, isAsync: boolean): string[] {
  const pg = plan.pagination!;
  const lines = signature(plan, false, `iter_${plan.name}`, `${isAsync ? 'AsyncIterator' : 'Iterator'}[${pg.itemType}]`);
  const what = pg.itemsIsObject ? `the \`\`${pg.itemsPath}\`\` object of every page` : `every item of \`\`${pg.itemsPath}\`\` across pages`;
  lines.push(...docstring(`${what} of \`\`${plan.name}\`\`, following \`\`${pg.nextTokenPath}\`\` -> \`\`${pg.nextTokenParam}\`\`.`, '        '));
  const kwargs = [...plan.params.map((p) => `${pyStr(p.py)}: ${p.py}`), ...(plan.body ? ['"body": body'] : []), '"request_options": request_options'];
  const tuple = (xs: string[]) => `(${xs.map(pyStr).join(', ')}${xs.length === 1 ? ',' : ''})`;
  const args = [`self.${plan.name}`, `{${kwargs.join(', ')}}`, `items=${tuple(pg.items)}`, `token=${tuple(pg.token)}`, `token_param=${pyStr(pg.nextTokenParam)},  # nosec B106`, `wire_items=${tuple(pg.itemsPath.split('.'))}`, `wire_token=${tuple(pg.nextTokenPath.split('.'))}`];
  if (pg.dropParamsOnNext) args.push('drop_params_on_next=True');
  if (pg.keepParams?.length) args.push(`keep_params=${tuple(pg.keepParams.map((k) => paramName(k)))}`);
  if (pg.itemsIsObject) args.push('single=True');
  lines.push(`        return ${isAsync ? 'apaginate' : 'paginate'}(`, ...args.map((a) => (a.includes('# nosec') ? `            ${a}` : `            ${a},`)), '        )');
  return lines;
}

export function renderResourceModule(ctx: EmitterContext, service: Service, plans: OpPlan[], module: string, imports: string[]): string {
  const body: string[] = [];
  for (const isAsync of [false, true]) {
    const cls = `${isAsync ? 'Async' : ''}${service.name}Resource`;
    body.push('', `class ${cls}:`);
    body.push(`    """${isAsync ? 'Asynchronous' : 'Synchronous'} \`\`${service.name}\`\` resource${service.description ? `: ${service.description.trim().split('\n')[0]}` : ''}."""`);
    body.push('', '    __slots__ = ("_http",)', '', `    def __init__(self, http: ${isAsync ? 'AsyncHttpClient' : 'HttpClient'}) -> None:`, '        self._http = http');
    for (const plan of plans) {
      body.push('', ...renderMethod(plan, isAsync));
      if (plan.pagination) body.push('', ...renderIterMethod(plan, isAsync));
    }
    body.push('');
  }
  const text = body.join('\n');
  const out: string[] = [];
  out.push(`"""\`\`${service.name}\`\` resource of ${ctx.spec.name}.`, '', HEADER_DOC, '"""', '', 'from __future__ import annotations', '');
  out.push(...importsFor(text), '');
  const helpers = ['AsyncHttpClient', 'HttpClient', 'RateLimit', 'RequestOptions', 'apaginate', 'joined', 'paginate', 'path_segment'].filter((n) => new RegExp(`\\b${n}\\b`).test(text));
  out.push(`from .._http import ${helpers.join(', ')}`, ...imports);
  out.push('', `SERVICE = ${pyStr(module)}`, '');
  out.push(text.trimEnd(), '', '', `__all__ = [${pyStr(`Async${service.name}Resource`)}, ${pyStr(`${service.name}Resource`)}]`, '');
  return out.join('\n');
}

// -- services -> resource modules ----------------------------------------------------------

export interface ResourceIndex {
  module: string;
  service: string;
  cls: string;
  operations: { operationId: string; method: string; httpMethod: string; path: string; paginated: boolean; rateLimit: boolean }[];
}

/** Resolved operations grouped by mount target (`mountRules` / `operationHints.mountOn` may merge or move services). */
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

export function generateResources(ctx: EmitterContext, notes: string[] = []): GeneratedFile[] {
  const packages = packagesOf(ctx);
  const opts = optionsOf(ctx);
  const files: GeneratedFile[] = [];
  const index: ResourceIndex[] = [];
  const modules = new Uniquer();
  for (const { service, ops } of resourceGroups(ctx)) {
    if (ops.length === 0) continue;
    const module = modules.take(resourceModuleOf(service.name, ops, packages));
    const pkg = packages.servicePkg.get(service.name) ?? module;
    const usedPkgs = new Set<string>();
    const place = (p: { pkg: string; cls: string } | undefined, fallback: string): string => {
      if (!p) return fallback;
      usedPkgs.add(p.pkg);
      return `${packages.alias(p.pkg)}.${p.cls}`;
    };
    const tctx: TypeContext = { model: (name) => place(packages.models.get(name), 'Any'), enum: (name) => place(packages.enums.get(name), 'str') };
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
    const imports = [...usedPkgs].sort().map((p) => importPackage(p, packages, '..models'));
    files.push(file(`resources/${module}.py`, renderResourceModule(ctx, service, plans, module, imports)));
    index.push({
      module,
      service: service.name,
      cls: `${service.name}Resource`,
      operations: plans.map((p) => ({ operationId: p.op.name, method: p.name, httpMethod: p.op.httpMethod.toUpperCase(), path: p.op.path, paginated: p.pagination !== null, rateLimit: p.rateLimit !== null })),
    });
  }
  files.push(file('resources/__init__.py', renderResourcesInit(ctx, index)));
  return files;
}

function renderResourcesInit(ctx: EmitterContext, index: ResourceIndex[]): string {
  const out: string[] = [];
  out.push(`"""Resources of ${ctx.spec.name}: one module per service, importable on demand.`, '', HEADER_DOC, '"""', '', 'from __future__ import annotations', '');
  out.push('#: resource module -> (sync class, async class)', 'SERVICES: dict[str, tuple[str, str]] = {');
  for (const s of index) out.push(`    ${pyStr(s.module)}: (${pyStr(s.cls)}, ${pyStr('Async' + s.cls)}),`);
  out.push('}', '');
  out.push('#: "<resource module>.<operationId>" -> (method name, HTTP method, path, paginated, has rate limit)', 'OPERATIONS: dict[str, tuple[str, str, str, bool, bool]] = {');
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
