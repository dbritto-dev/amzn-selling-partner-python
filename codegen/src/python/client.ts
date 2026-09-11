/** `client.py`: the top-level client (`--namespace`), one lazily created resource per service. */
import type { ApiSpec, EmitterContext, GeneratedFile } from '@workos/oagen';
import { compareVersions } from '../amazon.js';
import { HEADER_DOC, file } from './header.js';
import { docstring, pyStr } from './naming.js';
import { optionsOf, type EmitterOptions } from './options.js';
import { packagesOf, type Packages } from './packages.js';
import { apiVersionOf } from './pagination.js';
import { resourceGroups, resourceModuleOf } from './resources.js';

interface Entry {
  module: string;
  cls: string;
}

/** `<api>` -> latest `<api>_<version>` module, for services whose module carries a version suffix. */
export function latestAliases(modules: string[], extra: Record<string, string>): Map<string, string> {
  const byApi = new Map<string, { module: string; version: string }[]>();
  for (const m of modules) {
    const av = apiVersionOf(m);
    if (!av) continue;
    let list = byApi.get(av[0]);
    if (!list) byApi.set(av[0], (list = []));
    list.push({ module: m, version: av[1] });
  }
  const out = new Map<string, string>();
  const taken = new Set(modules);
  for (const [api, list] of byApi) {
    if (taken.has(api)) continue;
    list.sort((a, b) => compareVersions(a.version, b.version));
    out.set(api, list[list.length - 1]!.module);
  }
  for (const [alias, target] of Object.entries(extra)) {
    const resolvedTarget = out.get(target) ?? (taken.has(target) ? target : undefined);
    if (resolvedTarget && !taken.has(alias) && !out.has(alias)) out.set(alias, resolvedTarget);
  }
  return new Map([...out.entries()].sort((a, b) => a[0].localeCompare(b[0])));
}

function renderClass(name: string, isAsync: boolean, spec: ApiSpec, entries: Entry[], aliases: Map<string, string>): string[] {
  const http = isAsync ? 'AsyncHttpClient' : 'HttpClient';
  const lines: string[] = [];
  lines.push(`class ${name}:`);
  lines.push(...docstring(`${isAsync ? 'Asynchronous' : 'Synchronous'} client of ${spec.name} ${spec.version}.\n\nEvery resource is created on first access (\`\`client.${entries[0]?.module ?? 'service'}\`\`); keyword arguments configure the HTTP client (see \`\`http_client.${http}\`\`).`, '    '));
  lines.push('');
  lines.push('    def __init__(');
  lines.push('        self,');
  lines.push('        *,');
  lines.push(`        base_url: str = ${pyStr(spec.baseUrl)},`);
  lines.push(`        auth: ${isAsync ? 'AsyncAuth' : 'Auth'} | None = None,`);
  lines.push('        timeout: httpx2.Timeout | float | None = None,');
  lines.push('        max_retries: int = MAX_RETRIES,');
  lines.push('        throttle: bool = True,');
  lines.push('        default_rate_limit: RateLimit | None = None,');
  lines.push('        headers: Mapping[str, str] | None = None,');
  lines.push(`        transport: ${isAsync ? 'httpx2.AsyncBaseTransport' : 'httpx2.BaseTransport'} | None = None,`);
  lines.push(`        http_client: ${isAsync ? 'httpx2.AsyncClient' : 'httpx2.Client'} | None = None,`);
  lines.push('        request_id_header: str = REQUEST_ID_HEADER,');
  lines.push('        rate_hint_header: str | None = RATE_HINT_HEADER,');
  lines.push('        user_agent: str | None = None,');
  lines.push('        **kwargs: Any,');
  lines.push('    ) -> None:');
  lines.push(`        self._http = ${http}(`);
  for (const k of ['base_url', 'auth', 'timeout', 'max_retries', 'throttle', 'default_rate_limit', 'headers', 'transport', 'http_client', 'request_id_header', 'rate_hint_header', 'user_agent']) {
    lines.push(`            ${k}=${k},`);
  }
  lines.push('            **kwargs,');
  lines.push('        )');
  lines.push('');
  lines.push('    @property');
  lines.push(`    def http(self) -> ${http}:`);
  lines.push('        """The HTTP client every resource uses."""');
  lines.push('        return self._http');
  lines.push('');
  lines.push('    @property');
  lines.push('    def base_url(self) -> str:');
  lines.push('        return self._http.base_url');
  lines.push('');
  lines.push('    @property');
  lines.push(`    def http_client(self) -> ${isAsync ? 'httpx2.AsyncClient' : 'httpx2.Client'}:`);
  lines.push('        return self._http.http_client');
  lines.push('');
  if (isAsync) {
    lines.push('    async def aclose(self) -> None:', '        await self._http.aclose()', '');
    lines.push('    async def __aenter__(self) -> Self:', '        return self', '');
    lines.push('    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:', '        await self.aclose()');
  } else {
    lines.push('    def close(self) -> None:', '        self._http.close()', '');
    lines.push('    def __enter__(self) -> Self:', '        return self', '');
    lines.push('    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:', '        self.close()');
  }
  lines.push('', '    # -- resources ---------------------------------------------------------------');
  for (const e of entries) {
    const cls = `${isAsync ? 'Async' : ''}${e.cls}`;
    lines.push('', '    @cached_property', `    def ${e.module}(self) -> ${cls}:`, `        from .resources.${e.module} import ${cls}`, '', `        return ${cls}(self._http)`);
  }
  if (aliases.size) lines.push('', '    # -- latest version of each API ----------------------------------------------');
  for (const [alias, module] of aliases) {
    const cls = `${isAsync ? 'Async' : ''}${entries.find((e) => e.module === module)!.cls}`;
    lines.push('', '    @property', `    def ${alias}(self) -> ${cls}:`, `        """\`\`${module}\`\`."""`, `        return self.${module}`);
  }
  return lines;
}

export function renderClientModule(spec: ApiSpec, ctx: EmitterContext, packages: Packages, opts: EmitterOptions): string {
  const entries: Entry[] = resourceGroups(ctx).filter((g) => g.ops.length > 0).map((g) => ({ module: resourceModuleOf(g.service.name, g.ops, packages), cls: `${g.service.name}Client` }));
  const aliases = latestAliases(
    entries.map((e) => e.module),
    opts.serviceAliases,
  );
  const name = ctx.namespacePascal || 'Client';
  const out: string[] = [];
  out.push(`"""Clients of ${spec.name}.`, '', HEADER_DOC, '"""', '', 'from __future__ import annotations', '');
  out.push('from collections.abc import Mapping', 'from functools import cached_property', 'from types import TracebackType', 'from typing import TYPE_CHECKING, Any', '', 'import httpx2', '');
  out.push('from .http_client import MAX_RETRIES, RATE_HINT_HEADER, REQUEST_ID_HEADER, Auth, AsyncAuth, AsyncHttpClient, HttpClient, RateLimit', '');
  out.push('if TYPE_CHECKING:', '    from typing_extensions import Self', '');
  for (const e of entries) out.push(`    from .resources.${e.module} import Async${e.cls}, ${e.cls}`);
  out.push('', '');
  out.push(...renderClass(name, false, spec, entries, aliases), '', '');
  out.push(...renderClass(`Async${name}`, true, spec, entries, aliases), '', '');
  out.push(`__all__ = [${pyStr('Async' + name)}, ${pyStr(name)}]`, '');
  return out.join('\n');
}

export function generateClient(spec: ApiSpec, ctx: EmitterContext): GeneratedFile[] {
  return [file('client.py', renderClientModule(spec, ctx, packagesOf(ctx), optionsOf(ctx)))];
}
