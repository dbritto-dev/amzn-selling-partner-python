/**
 * Pagination detection over the oagen IR (docs/PLAN.md §9), plus the shape of
 * the descriptor emitted as a `Pagination(...)` literal.
 */
import type { ApiSpec, Model, Operation, TypeRef } from '@workos/oagen';

export interface PaginationDescriptor {
  itemsPath: string;
  nextTokenPath: string;
  nextTokenParam: string;
  prevTokenPath?: string;
  dropParamsOnNext?: boolean;
  keepParams?: string[];
  itemsIsObject?: boolean;
  source: 'heuristic' | 'override';
}

const TOKEN_NAMES = new Set(['nexttoken', 'pagetoken', 'paginationtoken']);
const CONTAINERS = ['payload', 'pagination'];

function unwrap(ref: TypeRef): TypeRef {
  return ref.kind === 'nullable' ? unwrap(ref.inner) : ref;
}

function modelOf(spec: ApiSpec, ref: TypeRef | undefined): Model | undefined {
  if (!ref) return undefined;
  const r = unwrap(ref);
  if (r.kind !== 'model') return undefined;
  return spec.models.find((m) => m.name === r.name);
}

function isString(ref: TypeRef): boolean {
  const r = unwrap(ref);
  return (r.kind === 'primitive' && r.type === 'string') || r.kind === 'enum';
}

function isArray(ref: TypeRef): boolean {
  return unwrap(ref).kind === 'array';
}

export interface DetectionLog {
  key: string;
  message: string;
}

export function detectPagination(spec: ApiSpec, op: Operation, key: string, log: DetectionLog[] = []): PaginationDescriptor | null {
  const tokenParam = op.queryParams.find((p) => TOKEN_NAMES.has(p.name.toLowerCase()));
  if (!tokenParam) return null;
  const root = modelOf(spec, op.response);
  if (!root) {
    log.push({ key, message: `has a ${tokenParam.name} parameter but no JSON object success schema; left unpaginated` });
    return null;
  }
  type Container = { prefix: string; model: Model; parent: Model | null };
  const containers: Container[] = [{ prefix: '', model: root, parent: null }];
  for (const c of CONTAINERS) {
    const field = root.fields.find((f) => f.name === c);
    const sub = field ? modelOf(spec, field.type) : undefined;
    if (sub) {
      containers.push({ prefix: c, model: sub, parent: root });
      if (c === 'payload') {
        const pag = sub.fields.find((f) => f.name === 'pagination');
        const pagModel = pag ? modelOf(spec, pag.type) : undefined;
        if (pagModel) containers.push({ prefix: 'payload.pagination', model: pagModel, parent: sub });
      }
    }
  }
  const wanted = new Set([tokenParam.name.toLowerCase(), 'nexttoken']);
  const candidates: { token: string; items: string; prev: string | undefined }[] = [];
  for (const { prefix, model, parent } of containers) {
    const tokenField = model.fields.find((f) => wanted.has(f.name.toLowerCase()) && isString(f.type));
    if (!tokenField) continue;
    let arrays = model.fields.filter((f) => isArray(f.type) && f.name !== 'errors').map((f) => f.name);
    let itemsPrefix = prefix;
    if (arrays.length === 0 && parent) {
      arrays = parent.fields.filter((f) => isArray(f.type) && f.name !== 'errors').map((f) => f.name);
      itemsPrefix = prefix.includes('.') ? prefix.slice(0, prefix.lastIndexOf('.')) : '';
    }
    const prevField = model.fields.find((f) => ['prevtoken', 'previoustoken', 'previouspagetoken'].includes(f.name.toLowerCase()));
    if (arrays.length === 1) {
      candidates.push({
        token: join(prefix, tokenField.name),
        items: join(itemsPrefix, arrays[0]!),
        prev: prevField ? join(prefix, prevField.name) : undefined,
      });
    } else {
      log.push({
        key,
        message: `token field ${join(prefix, tokenField.name)} found but ${arrays.length} array fields nearby (${arrays.join(', ') || 'none'}); left unpaginated`,
      });
      return null;
    }
  }
  if (candidates.length !== 1) {
    log.push({
      key,
      message: candidates.length
        ? `ambiguous (${candidates.length} candidates); left unpaginated`
        : `has a ${tokenParam.name} parameter but no matching token field in the response; left unpaginated`,
    });
    return null;
  }
  const c = candidates[0]!;
  return { itemsPath: c.items, nextTokenPath: c.token, nextTokenParam: tokenParam.name, prevTokenPath: c.prev, source: 'heuristic' };
}

function join(prefix: string, name: string): string {
  return prefix ? `${prefix}.${name}` : name;
}
