/** Resource file: one `Op(...)` literal per operation + Sync/Async resource classes. */
import type { ApiSpec, EmitterContext, GeneratedFile, Operation, Parameter, TypeRef, Model } from '@workos/oagen';
import { docstring, methodName, paramName, pyStr, Uniquer, fieldName } from './naming.js';
import { pyType, typeContext, type TypeContext } from './types.js';
import { parseRateLimit } from './ratelimits.js';
import { detectPagination, type PaginationDescriptor } from './pagination.js';
import type { EmitterOptions } from './options.js';

interface ParamPlan {
  py: string;
  wire: string;
  required: boolean;
  location: 'path' | 'query' | 'header';
  kind: 'scalar' | 'array' | 'object';
  style: string;
  explode: boolean;
  allowReserved: boolean;
  annotation: string;
}

interface OpPlan {
  op: Operation;
  name: string;
  key: string;
  varName: string;
  params: ParamPlan[];
  template: string;
  body: { kind: string; contentType: string; required: boolean; annotation: string } | null;
  defaultDecoder: string;
  decoders: Record<string, string>;
  errorDecoders: Record<string, string>;
  defaultError: string | null;
  streamDefault: boolean;
  returnType: string;
  itemType: string | null;
  rateLimit: { rate: number; burst: number } | null;
  pagination: PaginationDescriptor | null;
  doc: string;
}

function unwrap(ref: TypeRef): TypeRef {
  return ref.kind === 'nullable' ? unwrap(ref.inner) : ref;
}

function paramKind(ref: TypeRef): ParamPlan['kind'] {
  const r = unwrap(ref);
  if (r.kind === 'array') return 'array';
  if (r.kind === 'map' || r.kind === 'model') return 'object';
  return 'scalar';
}

function isVoid(ref: TypeRef): boolean {
  const r = unwrap(ref);
  return r.kind === 'primitive' && r.type === 'unknown';
}

function decoderExpr(ref: TypeRef, ctx: TypeContext): string {
  const t = pyType(ref, ctx);
  return `json_decoder(lambda: ${t})`;
}

function modelOf(spec: ApiSpec, ref: TypeRef | undefined): Model | undefined {
  if (!ref) return undefined;
  const r = unwrap(ref);
  return r.kind === 'model' ? spec.models.find((m) => m.name === r.name) : undefined;
}

/** Type of the page items for a pagination descriptor, resolved through the response model. */
function itemType(spec: ApiSpec, op: Operation, desc: PaginationDescriptor, ctx: TypeContext): string {
  let model = modelOf(spec, op.response);
  const parts = desc.itemsPath.split('.');
  let ref: TypeRef | undefined;
  for (const part of parts) {
    if (!model) return 'Any';
    const field = model.fields.find((f) => f.name === part);
    if (!field) return 'Any';
    ref = field.type;
    model = modelOf(spec, field.type);
  }
  if (!ref) return 'Any';
  const r = unwrap(ref);
  if (desc.itemsIsObject) return pyType(r, ctx);
  if (r.kind === 'array') return pyType(r.items, ctx);
  return 'Any';
}

export function planOperations(spec: ApiSpec, opts: EmitterOptions): OpPlan[] {
  const ctx = typeContext(spec, 'models.');
  const METHOD_ORDER = ['get', 'put', 'post', 'delete', 'patch', 'head', 'options', 'trace'];
  const ops = spec.services.flatMap((s) => s.operations);
  // spec order within a path (Swagger files list methods in a fixed order); stable otherwise
  const indexed = ops.map((op, i) => ({ op, i }));
  indexed.sort((a, b) => (a.op.path === b.op.path ? METHOD_ORDER.indexOf(a.op.httpMethod) - METHOD_ORDER.indexOf(b.op.httpMethod) || a.i - b.i : a.i - b.i));
  ops.splice(0, ops.length, ...indexed.map((x) => x.op));
  const names = new Map<string, number>();
  const plans: OpPlan[] = [];
  const varNames = new Uniquer();
  for (const op of ops) {
    const base = methodName(op.name);
    let name = base;
    if (names.has(base)) {
      name = `${base}_${op.httpMethod.toLowerCase()}`;
      let n = 2;
      while (names.has(name)) name = `${base}_${op.httpMethod.toLowerCase()}_${n++}`;
      opts.report?.notes.push(`${opts.api}.${opts.version}: duplicate operationId ${op.name}; exposing ${op.httpMethod.toUpperCase()} ${op.path} as ${name}()`);
    }
    names.set(name, 1);
    const httpKey = `${op.httpMethod.toUpperCase()} ${op.path}`;
    const extras = opts.extras[httpKey] ?? {};
    const used = new Uniquer(['self', 'raw', 'paginate', 'request_options', 'body']);
    const params: ParamPlan[] = [];
    // path params in template order
    let template = op.path;
    const greedy = new Set(extras.greedyPathParams ?? []);
    for (const m of op.path.matchAll(/\{([^{}]+)\}/g)) {
      const wire = m[1]!;
      const p: Parameter = op.pathParams.find((x) => x.name === wire) ?? { name: wire, type: { kind: 'primitive', type: 'string' }, required: true };
      params.push({
        py: used.take(paramName(wire)),
        wire,
        required: true,
        location: 'path',
        kind: paramKind(p.type),
        style: p.style ?? 'simple',
        explode: p.explode ?? false,
        allowReserved: greedy.has(wire),
        annotation: pyType(p.type, ctx),
      });
      template = template.replace(`{${wire}}`, '{}');
    }
    for (const p of op.queryParams) {
      params.push({
        py: used.take(paramName(p.name)),
        wire: p.name,
        required: p.required,
        location: 'query',
        kind: paramKind(p.type),
        style: p.style ?? 'form',
        explode: p.explode ?? true,
        allowReserved: false,
        annotation: pyType(p.type, ctx),
      });
    }
    for (const p of op.headerParams) {
      params.push({
        py: used.take(paramName(p.name)),
        wire: p.name,
        required: p.required,
        location: 'header',
        kind: paramKind(p.type),
        style: 'simple',
        explode: p.explode ?? false,
        allowReserved: false,
        annotation: pyType(p.type, ctx),
      });
    }
    if (op.cookieParams?.length) {
      opts.report?.notes.push(`${opts.api}.${opts.version}.${op.name}: cookie parameters are not supported and are ignored`);
    }
    let body: OpPlan['body'] = null;
    if (op.requestBody) {
      const enc = op.requestBodyEncoding ?? 'json';
      const required = extras.bodyRequired ?? true;
      const t = pyType(op.requestBody, ctx);
      const isModel = unwrap(op.requestBody).kind === 'model';
      if (enc === 'json') body = { kind: 'json', contentType: 'application/json', required, annotation: isModel ? `${t} | Mapping[str, Any]` : t };
      else if (enc === 'form-data') body = { kind: 'multipart', contentType: 'multipart/form-data', required, annotation: 'bytes | dict[str, Any]' };
      else if (enc === 'form-urlencoded') body = { kind: 'form', contentType: 'application/x-www-form-urlencoded', required, annotation: 'bytes | dict[str, Any]' };
      else if (enc === 'text') body = { kind: 'text', contentType: 'text/plain', required, annotation: 'str' };
      else body = { kind: 'binary', contentType: 'application/octet-stream', required, annotation: 'bytes' };
    }
    // success decoders
    const decoders: Record<string, string> = {};
    let defaultDecoder = 'NONE';
    let returnType = 'None';
    let streamDefault = false;
    const mediaOf = (code: string): string[] => extras.successMedia?.[code] ?? [];
    const nonJsonDecoder = (code: string): string | null => {
      const media = mediaOf(code);
      if (media.length === 0 || media.some((m) => m.includes('json'))) return null;
      if (media.some((m) => m === 'text/event-stream')) return 'BYTES';
      if (media.every((m) => m.startsWith('text/'))) return 'TEXT';
      return 'BYTES';
    };
    const firstSuccess = Object.keys(extras.successCodes ?? {}).sort()[0];
    if (firstSuccess && mediaOf(firstSuccess).includes('text/event-stream')) streamDefault = true;
    if (firstSuccess && nonJsonDecoder(firstSuccess)) {
      defaultDecoder = nonJsonDecoder(firstSuccess)!;
      returnType = defaultDecoder === 'TEXT' ? 'str' : 'bytes';
      for (const code of Object.keys(extras.successCodes ?? {})) {
        const d = nonJsonDecoder(code);
        if (d && d !== defaultDecoder) decoders[code] = d;
        else if (!d && !(extras.successCodes ?? {})[code]) decoders[code] = 'NONE';
      }
    } else if (op.successResponses && op.successResponses.length > 1) {
      const types: string[] = [];
      for (const r of op.successResponses) {
        if (isVoid(r.type)) {
          decoders[String(r.statusCode)] = 'NONE';
          types.push('None');
        } else {
          decoders[String(r.statusCode)] = decoderExpr(r.type, ctx);
          types.push(pyType(r.type, ctx));
        }
      }
      const first = op.successResponses.find((r) => !isVoid(r.type));
      defaultDecoder = first ? decoderExpr(first.type, ctx) : 'NONE';
      returnType = [...new Set(types)].join(' | ');
    } else if (!isVoid(op.response)) {
      defaultDecoder = decoderExpr(op.response, ctx);
      returnType = pyType(op.response, ctx);
      for (const [code, hasSchema] of Object.entries(extras.successCodes ?? {})) {
        if (!hasSchema) decoders[code] = 'NONE';
      }
    } else {
      for (const [code, hasSchema] of Object.entries(extras.successCodes ?? {})) {
        if (hasSchema) opts.report?.notes.push(`${opts.api}.${opts.version}.${op.name}: ${code} declares a schema oagen did not type; decoded as None`);
      }
    }
    const errorDecoders: Record<string, string> = {};
    let defaultError: string | null = null;
    for (const e of op.errors) {
      if (!e.type || isVoid(e.type)) continue;
      errorDecoders[String(e.statusCode)] = decoderExpr(e.type, ctx);
    }
    if (extras.defaultErrorRef && ctx.known.has(extras.defaultErrorRef)) {
      defaultError = decoderExpr({ kind: 'model', name: extras.defaultErrorRef }, ctx);
    } else if (Object.keys(errorDecoders).length) {
      defaultError = errorDecoders['400'] ?? Object.values(errorDecoders)[0]!;
    }

    const key = `${opts.api}.${opts.version}.${op.name}`;
    let rateLimit: OpPlan['rateLimit'] = null;
    if (opts.amazon) {
      rateLimit = parseRateLimit(op.description);
      if (!rateLimit) opts.report?.unparsedRateLimits.push(key);
    }
    let pagination: PaginationDescriptor | null = null;
    const override = opts.paginationOverride?.(op.name);
    if (override) {
      pagination = override;
    } else {
      const log: { key: string; message: string }[] = [];
      const detected = detectPagination(spec, op, key, log);
      for (const l of log) opts.report?.notes.push(`pagination: ${l.key}: ${l.message}`);
      if (detected) {
        pagination = opts.dropParamsOnNext?.(op.name) ? { ...detected, dropParamsOnNext: true, source: 'override' } : detected;
      }
    }
    if (pagination) {
      const tokenParam = params.find((p) => (p.location === 'query' || p.location === 'header') && p.wire === pagination!.nextTokenParam);
      if (!tokenParam) {
        opts.report?.notes.push(`pagination: ${key}: next_token_param ${pagination.nextTokenParam} is not a parameter; descriptor dropped`);
        pagination = null;
      }
    }
    if (pagination && opts.report) opts.report.pagination[key] = `${pagination.source}: items=${pagination.itemsPath} token=${pagination.nextTokenPath}`;
    let item: string | null = null;
    if (pagination) {
      item = itemType(spec, op, pagination, ctx);
    }
    const docParts: string[] = [];
    if (extras.summary && !(op.description ?? '').trim().startsWith(extras.summary.trim())) docParts.push(extras.summary.trim());
    if (op.description) docParts.push(op.description.trim());
    if (op.deprecated) docParts.push('Deprecated.');
    docParts.push(`${op.httpMethod.toUpperCase()} ${op.path}`);
    plans.push({
      op,
      name,
      key,
      varName: varNames.take(`_op_${name}`),
      params,
      template,
      body,
      defaultDecoder,
      decoders,
      errorDecoders,
      defaultError,
      streamDefault,
      returnType,
      itemType: item,
      rateLimit,
      pagination,
      doc: docParts.join('\n\n'),
    });
  }
  return plans;
}

function paramLiteral(p: ParamPlan): string {
  const args = [pyStr(p.py), pyStr(p.wire)];
  if (p.location !== 'path' && p.required) args.push('required=True');
  if (p.kind !== 'scalar') args.push(`kind=${pyStr(p.kind)}`);
  const defaultStyle = p.location === 'query' ? 'form' : 'simple';
  if (p.style !== defaultStyle) args.push(`style=${pyStr(p.style)}`);
  const defaultExplode = p.location === 'query';
  if (p.explode !== defaultExplode) args.push(`explode=${p.explode ? 'True' : 'False'}`);
  if (p.allowReserved) args.push('allow_reserved=True');
  return `${p.location}(${args.join(', ')})`;
}

function paginationLiteral(d: PaginationDescriptor): string {
  const args = [`items_path=${pyStr(d.itemsPath)}`, `next_token_path=${pyStr(d.nextTokenPath)}`, `next_token_param=${pyStr(d.nextTokenParam)}`];
  if (d.prevTokenPath) args.push(`prev_token_path=${pyStr(d.prevTokenPath)}`);
  if (d.dropParamsOnNext) args.push('drop_params_on_next=True');
  if (d.keepParams?.length) args.push(`keep_params=(${d.keepParams.map(pyStr).join(', ')},)`);
  if (d.itemsIsObject) args.push('items_is_object=True');
  args.push(`source=${pyStr(d.source === 'override' ? 'plugin' : 'heuristic')}`);
  return `Pagination(${args.join(', ')})`;
}

function renderOp(plan: OpPlan, opts: EmitterOptions): string[] {
  const { op } = plan;
  const lines: string[] = [];
  const decoderVars: string[] = [];
  const decoderName = new Map<string, string>();
  const decoderRef = (expr: string): string => {
    if (expr === 'NONE') return 'NONE';
    let v = decoderName.get(expr);
    if (!v) {
      v = `${plan.varName}_d${decoderVars.length + 1}`;
      decoderName.set(expr, v);
      decoderVars.push(`${v} = ${expr}`);
    }
    return v;
  };
  const defaultDecoder = decoderRef(plan.defaultDecoder);
  const decoders = Object.entries(plan.decoders).map(([c, e]) => `${c}: ${decoderRef(e)}`);
  const errors = Object.entries(plan.errorDecoders).map(([c, e]) => `${c}: ${decoderRef(e)}`);
  const defaultError = plan.defaultError ? decoderRef(plan.defaultError) : 'None';
  lines.push(...decoderVars);
  lines.push(`${plan.varName} = Op(`);
  lines.push(`    key=${pyStr(plan.key)},`);
  lines.push(`    name=${pyStr(plan.name)},`);
  lines.push(`    operation_id=${pyStr(op.name)},`);
  lines.push(`    api=${pyStr(opts.api)},`);
  lines.push(`    version=${pyStr(opts.version)},`);
  lines.push(`    method=${pyStr(op.httpMethod.toUpperCase())},`);
  lines.push(`    path=${pyStr(op.path)},`);
  lines.push(`    url_template=${pyStr(plan.template)},`);
  const byLoc = (loc: ParamPlan['location']) => plan.params.filter((p) => p.location === loc);
  for (const loc of ['path', 'query', 'header'] as const) {
    const ps = byLoc(loc);
    if (ps.length === 0) lines.push(`    ${loc}_params=(),`);
    else {
      lines.push(`    ${loc}_params=(`);
      for (const p of ps) lines.push(`        ${paramLiteral(p)},`);
      lines.push('    ),');
    }
  }
  if (plan.body) {
    lines.push(`    body=Body(${pyStr(plan.body.kind)}, ${pyStr(plan.body.contentType)}, required=${plan.body.required ? 'True' : 'False'}),`);
  }
  lines.push(`    default_decoder=${defaultDecoder},`);
  if (decoders.length) lines.push(`    decoders={${decoders.join(', ')}},`);
  if (errors.length) lines.push(`    error_decoders={${errors.join(', ')}},`);
  if (defaultError !== 'None') lines.push(`    default_error=${defaultError},`);
  if (plan.streamDefault) lines.push('    stream_default=True,');
  if (plan.rateLimit) lines.push(`    rate_limit=RateLimit(rate=${plan.rateLimit.rate}, burst=${plan.rateLimit.burst}),`);
  if (plan.pagination) lines.push(`    pagination=${paginationLiteral(plan.pagination)},`);
  if (op.deprecated) lines.push('    deprecated=True,');
  lines.push(`    doc=${pyStr(plan.doc)},`);
  lines.push(')');
  return lines;
}

function signature(plan: OpPlan, isAsync: boolean): string[] {
  const parts: string[] = ['self', '*'];
  const required = plan.params.filter((p) => p.required);
  const optional = plan.params.filter((p) => !p.required);
  for (const p of required) parts.push(`${p.py}: ${p.annotation}`);
  if (plan.body?.required) parts.push(`body: ${plan.body.annotation}`);
  for (const p of optional) parts.push(`${p.py}: ${p.annotation} | NotGiven = NOT_GIVEN`);
  if (plan.body && !plan.body.required) parts.push(`body: ${plan.body.annotation} | NotGiven = NOT_GIVEN`);
  parts.push('raw: bool = False', 'paginate: Pagination | None | NotGiven = NOT_GIVEN', 'request_options: RequestOptions | None = None');
  let ret = plan.returnType;
  if (plan.pagination) ret = `${isAsync ? 'AsyncPage' : 'SyncPage'}[${plan.itemType ?? 'Any'}]`;
  if (plan.streamDefault) ret = isAsync ? 'AsyncStream' : 'Stream';
  const def = isAsync ? 'async def' : 'def';
  return [`    ${def} ${plan.name}(`, ...parts.map((p) => `        ${p},`), `    ) -> ${ret}:`];
}

function methodBody(plan: OpPlan, isAsync: boolean): string[] {
  const lines: string[] = [];
  lines.push(...docstring(plan.doc, '        '));
  const kw = plan.params.map((p) => `${pyStr(p.py)}: ${p.py}`);
  if (plan.body) kw.push('"body": body');
  const call = `self._client.call(${plan.varName}, {${kw.join(', ')}}, raw, paginate, request_options)`;
  lines.push(`        return ${isAsync ? 'await ' : ''}${call}`);
  return lines;
}

export function renderResourceModule(spec: ApiSpec, plans: OpPlan[], opts: EmitterOptions, classBase: string): string {
  const out: string[] = [];
  const cls = classBase;
  out.push(`"""Operations of ${opts.api} ${opts.version} (${spec.name}).`);
  out.push('');
  out.push('Generated by codegen/ (oagen) from the pinned spec; do not edit by hand.');
  out.push('"""');
  out.push('');
  out.push('from __future__ import annotations');
  out.push('');
  const body: string[] = [];
  for (const plan of plans) body.push(...renderOp(plan, opts), '');
  for (const isAsync of [false, true]) {
    body.push('');
    body.push(`class ${isAsync ? 'Async' : ''}${cls}(${isAsync ? 'AsyncResource' : 'SyncResource'}):`);
    body.push(`    """${isAsync ? 'Async' : 'Sync'} resource for ${opts.api} ${opts.version}."""`);
    body.push('');
    body.push('    __slots__ = ()');
    body.push(`    _resource_name = ${pyStr(`${opts.api}.${opts.version}`)}`);
    body.push(`    models = models`);
    body.push(`    _ops = {${plans.map((p) => `${pyStr(p.name)}: ${p.varName}`).join(', ')}}`);
    for (const plan of plans) {
      body.push('');
      body.push(...signature(plan, isAsync));
      body.push(...methodBody(plan, isAsync));
    }
    body.push('');
  }
  const text = body.join('\n');
  const typingNames = ['Any', 'Literal'].filter((n) => new RegExp(`\\b${n}\\b`).test(text));
  if (text.includes('datetime.')) out.push('import datetime');
  const collections = ['Mapping'].filter((n) => new RegExp(`\\b${n}\\b`).test(text));
  if (collections.length) out.push(`from collections.abc import ${collections.join(', ')}`);
  if (typingNames.length) out.push(`from typing import ${typingNames.join(', ')}`);
  out.push('');
  const rt = `${opts.runtimePackage}.runtime`;
  out.push(`from ${opts.packageName}.models.${opts.api} import ${opts.version} as models`);
  const opNames = ['BYTES', 'NONE', 'TEXT', 'Body', 'Op', 'header', 'json_decoder', 'path', 'query'].filter((n) =>
    new RegExp(/^[A-Z]+$/.test(n) ? `\\b${n}\\b` : `\\b${n}\\(`).test(text),
  );
  out.push(`from ${rt}._op import ${opNames.join(', ')}`);
  const pagNames = ['AsyncPage', 'Pagination', 'SyncPage'].filter((n) => new RegExp(`\\b${n}\\b`).test(text));
  out.push(`from ${rt}._pagination import ${pagNames.join(', ')}`);
  out.push(`from ${rt}._resources import AsyncResource, SyncResource`);
  if (/\b(Async)?Stream\b/.test(text)) out.push(`from ${rt}._stream import AsyncStream, Stream`);
  if (text.includes('RateLimit(')) out.push(`from ${rt}._throttle import RateLimit`);
  out.push(`from ${rt}._types import NOT_GIVEN, NotGiven, RequestOptions`);
  out.push('');
  out.push(text.trimEnd());
  out.push('');
  out.push('');
  out.push(`__all__ = [${pyStr('Async' + cls)}, ${pyStr(cls)}]`);
  out.push('');
  return out.join('\n');
}

export function generateResources(spec: ApiSpec, _ctx: EmitterContext, opts: EmitterOptions, classBase: string): GeneratedFile[] {
  const plans = planOperations(spec, opts);
  if (plans.length === 0) return [];
  return [{ path: `resources/${opts.api}/${opts.version}.py`, content: renderResourceModule(spec, plans, opts, classBase), headerPlacement: 'skip' }];
}

export { fieldName };
