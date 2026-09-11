/**
 * The root client (`client.py`, the `--namespace` class and its async twin),
 * the package `__init__.py`, the exception hierarchy (`errors.py`, from the
 * spec's error policy) and the HTTP layer (`_http.py`, whose retry, backoff
 * and timeout constants come from the SDK behavior in the IR, never hardcoded).
 */
import type { ApiSpec, EmitterContext, GeneratedFile } from '@workos/oagen';
import { compareVersions } from '../amazon.js';
import { HEADER_DOC, docstring, file, pyStr } from './naming.js';
import { packagesOf } from './models.js';
import { apiVersionOf } from './pagination.js';
import { optionsOf, resourceGroups, resourceModuleOf, type EmitterOptions } from './resources.js';

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

const CLIENT_KWARGS = ['base_url', 'auth', 'timeout', 'max_retries', 'throttle', 'default_rate_limit', 'default_headers', 'transport', 'http_client', 'user_agent'];

function renderClass(name: string, isAsync: boolean, spec: ApiSpec, entries: Entry[], aliases: Map<string, string>): string[] {
  const http = isAsync ? 'AsyncHttpClient' : 'HttpClient';
  const hx = isAsync ? 'httpx2.AsyncClient' : 'httpx2.Client';
  const lines: string[] = [`class ${name}:`];
  lines.push(...docstring(`${isAsync ? 'Asynchronous' : 'Synchronous'} client of ${spec.name} ${spec.version}.\n\nOne resource per service, created on first access (\`\`client.${entries[0]?.module ?? 'service'}.<method>()\`\`).\nKeyword arguments configure the HTTP layer; \`\`with_options()\`\` derives a client\nwith some of them changed that shares the connection pool.`, '    '));
  lines.push('', '    def __init__(', '        self,', '        *,');
  lines.push(`        base_url: str = ${pyStr(spec.baseUrl)},`);
  lines.push(`        auth: ${isAsync ? 'AsyncAuth' : 'Auth'} | None = None,`);
  lines.push('        timeout: httpx2.Timeout | float | None = None,');
  lines.push('        max_retries: int = MAX_RETRIES,');
  lines.push('        throttle: bool = True,');
  lines.push('        default_rate_limit: RateLimit | None = None,');
  lines.push('        default_headers: Mapping[str, str] | None = None,');
  lines.push(`        transport: ${isAsync ? 'httpx2.AsyncBaseTransport' : 'httpx2.BaseTransport'} | None = None,`);
  lines.push(`        http_client: ${hx} | None = None,`);
  lines.push('        user_agent: str | None = None,');
  lines.push('        **kwargs: Any,');
  lines.push('    ) -> None:');
  lines.push(`        self._http = ${http}(`, ...CLIENT_KWARGS.map((k) => `            ${k}=${k},`), '            **kwargs,', '        )');
  lines.push('');
  lines.push('    @property', `    def http(self) -> ${http}:`, '        """The HTTP layer every resource uses."""', '        return self._http', '');
  lines.push('    @property', '    def base_url(self) -> str:', '        return self._http.base_url', '');
  lines.push('    @property', `    def http_client(self) -> ${hx}:`, '        return self._http.http_client', '');
  lines.push('    def with_options(self, **options: Any) -> Self:');
  lines.push('        """A copy of this client with some constructor options changed (shares the connection pool)."""');
  lines.push('        new = copy.copy(self)');
  lines.push('        new._http = self._http.with_options(**options)');
  lines.push('        for resource in _RESOURCES:');
  lines.push('            new.__dict__.pop(resource, None)');
  lines.push('        return new', '');
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

export function renderClientModule(spec: ApiSpec, ctx: EmitterContext, opts: EmitterOptions): string {
  const packages = packagesOf(ctx);
  const entries: Entry[] = resourceGroups(ctx)
    .filter((g) => g.ops.length > 0)
    .map((g) => ({ module: resourceModuleOf(g.service.name, g.ops, packages), cls: `${g.service.name}Resource` }));
  const aliases = latestAliases(entries.map((e) => e.module), opts.serviceAliases);
  const name = ctx.namespacePascal || 'Client';
  const out: string[] = [];
  out.push(`"""Clients of ${spec.name}.`, '', HEADER_DOC, '"""', '', 'from __future__ import annotations', '');
  out.push('import copy', 'from collections.abc import Mapping', 'from functools import cached_property', 'from types import TracebackType', 'from typing import TYPE_CHECKING, Any', '', 'import httpx2', '');
  out.push('from ._http import MAX_RETRIES, AsyncAuth, AsyncHttpClient, Auth, HttpClient, RateLimit', '');
  out.push('if TYPE_CHECKING:', '    from typing_extensions import Self', '');
  for (const e of entries) out.push(`    from .resources.${e.module} import Async${e.cls}, ${e.cls}`);
  out.push('', `_RESOURCES = (${entries.map((e) => pyStr(e.module)).join(', ')}${entries.length === 1 ? ',' : ''})`, '', '');
  out.push(...renderClass(name, false, spec, entries, aliases), '', '');
  out.push(...renderClass(`Async${name}`, true, spec, entries, aliases), '', '');
  out.push(`__all__ = [${pyStr('Async' + name)}, ${pyStr(name)}]`, '');
  return out.join('\n');
}

export function renderInitModule(spec: ApiSpec, ctx: EmitterContext, opts: EmitterOptions): string {
  const name = ctx.namespacePascal || 'Client';
  const errors = [...errorClasses(opts), 'APIConnectionError', 'APIError', 'APIResponseValidationError', 'APIStatusError', 'APITimeoutError'].sort();
  const http = ['RateLimit', 'RequestContext', 'RequestOptions'];
  const all = [`Async${name}`, name, ...errors, ...http].sort();
  return [
    `"""${spec.name} ${spec.version} SDK.`,
    '',
    `\`\`Async${name}\`\` (and its synchronous twin \`\`${name}\`\`) expose one resource per service; \`\`models\`\` holds the`,
    'pydantic models, ``errors`` the exceptions and ``_http`` the HTTP layer.',
    '',
    HEADER_DOC,
    '"""',
    '',
    'from __future__ import annotations',
    '',
    `from ._http import ${http.join(', ')}`,
    `from .client import Async${name}, ${name}`,
    `from .errors import ${errors.join(', ')}`,
    '',
    '__all__ = [',
    ...all.map((n) => `    ${pyStr(n)},`),
    ']',
    '',
  ].join('\n');
}

export function generateClient(spec: ApiSpec, ctx: EmitterContext): GeneratedFile[] {
  const opts = optionsOf(ctx);
  return [file('client.py', renderClientModule(spec, ctx, opts)), file('__init__.py', renderInitModule(spec, ctx, opts))];
}

// -- errors.py -----------------------------------------------------------------------------

export function errorClassName(kind: string): string {
  return kind.endsWith('Error') ? kind : `${kind}Error`;
}

function errorClasses(opts: EmitterOptions): string[] {
  const policy = opts.sdk.errors;
  return [...new Set([...Object.values(policy.statusCodeMap).map(errorClassName), errorClassName(policy.serverErrorKind)])];
}

export function renderErrorsModule(ctx: EmitterContext, opts: EmitterOptions): string {
  const policy = opts.sdk.errors;
  const server = errorClassName(policy.serverErrorKind);
  const entries = Object.entries(policy.statusCodeMap)
    .map(([code, kind]) => [Number(code), errorClassName(kind)] as const)
    .sort((a, b) => a[0] - b[0]);
  const classes = [...new Set(entries.map(([, cls]) => cls))];
  const out: string[] = [];
  out.push(`"""Exceptions raised by the ${ctx.spec.name} client.

\`\`APIError\`\` is the base; transport problems become \`\`APIConnectionError\`\` /
\`\`APITimeoutError\`\` and non-2xx responses become \`\`APIStatusError\`\` or one of
its status-specific subclasses (\`\`STATUS_ERRORS\`\`, from the spec's error
policy). \`\`APIStatusError.body\`\` holds the decoded error payload when the
spec's error schema validated, otherwise the raw JSON (or the bytes when the
body is not JSON).

${HEADER_DOC}
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx2


class APIError(Exception):
    """Base class for every error raised by the client."""

    message: str
    request: httpx2.Request | None

    def __init__(self, message: str, *, request: httpx2.Request | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.request = request


class APIConnectionError(APIError):
    """The request never produced a response (DNS, TLS, connection reset, ...)."""

    def __init__(self, message: str = "Connection error.", *, request: httpx2.Request | None = None, cause: BaseException | None = None) -> None:
        super().__init__(message, request=request)
        self.__cause__ = cause


class APITimeoutError(APIConnectionError):
    """The request timed out (connect, read, write or pool timeout)."""

    def __init__(self, message: str = "Request timed out.", *, request: httpx2.Request | None = None, cause: BaseException | None = None) -> None:
        super().__init__(message, request=request, cause=cause)


class APIStatusError(APIError):
    """A response with a non-success status code."""

    status_code: int
    response: httpx2.Response
    body: Any
    request_id: str | None
    #: Server-suggested delay in seconds (\`\`Retry-After\`\`), if any.
    retry_after: float | None

    def __init__(
        self, message: str, *, response: httpx2.Response, body: Any, request_id: str | None = None, retry_after: float | None = None
    ) -> None:
        super().__init__(message, request=response.request)
        self.status_code = response.status_code
        self.response = response
        self.body = body
        self.request_id = request_id
        self.retry_after = retry_after

    def __str__(self) -> str:
        rid = f" (request id: {self.request_id})" if self.request_id else ""
        return f"{self.message}{rid}"


class APIResponseValidationError(APIError):
    """A success response whose body did not validate against the spec's schema."""

    response: httpx2.Response
    body: bytes
    cause: BaseException

    def __init__(self, message: str, *, response: httpx2.Response, cause: BaseException) -> None:
        super().__init__(message, request=response.request)
        self.response = response
        self.body = response.content
        self.cause = cause
        self.__cause__ = cause

    @property
    def status_code(self) -> int:
        return self.response.status_code
`);
  for (const cls of classes) {
    const codes = entries.filter(([, c]) => c === cls).map(([code]) => code);
    out.push('', '', `class ${cls}(APIStatusError):`, `    """HTTP ${codes.join(' / ')}."""`);
  }
  out.push('', '', `class ${server}(APIStatusError):`, '    """Any 5xx."""', '', '');
  out.push('STATUS_ERRORS: dict[int, type[APIStatusError]] = {', ...entries.map(([code, cls]) => `    ${code}: ${cls},`), '}', '', '');
  out.push('def status_error_class(status_code: int) -> type[APIStatusError]:');
  out.push('    cls = STATUS_ERRORS.get(status_code)');
  out.push('    if cls is not None:', '        return cls');
  out.push('    if status_code >= 500:', `        return ${server}`);
  out.push('    return APIStatusError', '', '');
  const all = ['APIConnectionError', 'APIError', 'APIResponseValidationError', 'APIStatusError', 'APITimeoutError', 'STATUS_ERRORS', ...classes, server, 'status_error_class'].sort();
  out.push('__all__ = [', ...all.map((n) => `    ${pyStr(n)},`), ']', '');
  return out.join('\n');
}

export function generateErrors(ctx: EmitterContext): GeneratedFile[] {
  const opts = optionsOf(ctx);
  return [file('errors.py', renderErrorsModule(ctx, opts)), file('_http.py', renderHttpModule(ctx, opts))];
}

// -- _http.py ------------------------------------------------------------------------------

/** Retry/timeout policy is read from the IR, not hardcoded. */
export function renderHttpModule(ctx: EmitterContext, opts: EmitterOptions): string {
  const sdk = opts.sdk;
  const retry = sdk.retry;
  const timeoutEnv = sdk.timeout.timeoutEnvVar;
  const timeoutExpr = timeoutEnv ? `float(os.environ.get(${pyStr(timeoutEnv)}, ${sdk.timeout.defaultTimeoutSeconds}))` : String(sdk.timeout.defaultTimeoutSeconds);
  const rateHint = opts.rateHintHeader ? pyStr(opts.rateHintHeader) : 'None';
  return `"""HTTP layer of the ${ctx.spec.name} SDK, built on httpx2.

URL and query encoding, headers, timeouts, connection pooling, proxies and
connection retries are httpx2's. This module adds what the spec's SDK behavior
asks for on top: retries on retryable status codes with backoff
(\`\`Retry-After\`\` honoured), a per-operation token bucket, an auth hook that
sees the operation, decoding into the model each method names, pagination.

${HEADER_DOC}
"""

from __future__ import annotations

import asyncio
import datetime
import email.utils
import enum
import importlib.util
import logging
import os
import random
import threading
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import TYPE_CHECKING, Any, Protocol, cast
from urllib.parse import quote

import httpx2
from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_core import from_json, to_json

from .errors import APIConnectionError, APIResponseValidationError, APIStatusError, APITimeoutError, status_error_class
from .models._base import adapter_for

if TYPE_CHECKING:
    from typing_extensions import Self

log = logging.getLogger(${pyStr(ctx.namespace.toLowerCase() + '.http')})

# -- policy (from the spec's SDK behavior) ------------------------------------------------

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({${retry.retryableStatusCodes.join(', ')}})
MAX_RETRIES = ${retry.maxRetries}
RETRY_ON_CONNECTION_ERROR = ${retry.retryOnConnectionError ? 'True' : 'False'}
RETRY_ON_TIMEOUT = ${retry.retryOnTimeout ? 'True' : 'False'}
INITIAL_DELAY = ${retry.backoff.initialDelay}
BACKOFF_MULTIPLIER = ${retry.backoff.multiplier}
MAX_DELAY = ${retry.backoff.maxDelay}
JITTER_FACTOR = ${retry.backoff.jitterFactor}
DEFAULT_TIMEOUT = ${timeoutExpr}
REQUEST_ID_HEADER = ${pyStr(opts.requestIdHeader)}
RATE_HINT_HEADER: str | None = ${rateHint}
SDK_NAME = ${pyStr(opts.distribution)}


def _user_agent() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        v = version(SDK_NAME.replace("_", "-"))
    except PackageNotFoundError:
        v = "0.0.0"
    return f"{SDK_NAME}/{v} httpx2/{httpx2.__version__}"


# -- value encoding ----------------------------------------------------------------------


def scalar(value: Any) -> str:
    """String form of a parameter value (bool, datetime and Enum aware); httpx2 percent-encodes it."""
    if isinstance(value, enum.Enum):  # before str: a str enum without __str__ would render as "Name.MEMBER"
        return scalar(value.value)
    if isinstance(value, str):
        return value
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            return value.isoformat(timespec="milliseconds") + "Z"
        s = value.isoformat(timespec="milliseconds")
        return s[:-6] + "Z" if s.endswith("+00:00") else s
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def path_segment(value: Any, *, greedy: bool = False) -> str:
    """Percent-encode a path parameter (\`\`greedy\`\` keeps \`\`/\`\`)."""
    if value is None:
        raise TypeError("path parameters must not be None")
    return quote(scalar(value), safe="/" if greedy else "")


def joined(values: Any, sep: str = ",") -> str | None:
    """Join an array parameter with \`\`sep\`\` (\`\`None\`\` stays \`\`None\`\`)."""
    if values is None:
        return None
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        return scalar(values)
    return sep.join(scalar(v) for v in cast(Sequence[Any], values))


def _query(params: Mapping[str, Any] | None) -> list[tuple[str, str]]:
    """\`\`(key, value)\`\` pairs for httpx2: \`\`None\`\` values are omitted, lists repeat the key."""
    out: list[tuple[str, str]] = []
    for key, value in (params or {}).items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            out.extend((key, scalar(v)) for v in cast(Sequence[Any], value) if v is not None)
        elif isinstance(value, Mapping):  # deepObject style: key[prop]=value
            out.extend((f"{key}[{prop}]", scalar(v)) for prop, v in cast(Mapping[str, Any], value).items() if v is not None)
        else:
            out.append((key, scalar(value)))
    return out


def _headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    return {k: scalar(v) for k, v in (headers or {}).items() if v is not None}


# -- throttling ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class RateLimit:
    """Requests per second + burst of one operation (from the usage-plan table in its description)."""

    rate: float
    burst: int

    def __post_init__(self) -> None:
        if self.rate <= 0 or self.burst <= 0:
            raise ValueError("rate and burst must be positive")


class _TokenBucketState:
    """Token bucket bookkeeping shared by the blocking and the awaiting bucket."""

    __slots__ = ("_burst", "_lock", "_penalty_until", "_rate", "_tokens", "_updated")

    def __init__(self, limit: RateLimit) -> None:
        self._rate = limit.rate
        self._burst = float(limit.burst)
        self._tokens = float(limit.burst)
        self._updated = time.monotonic()
        self._penalty_until = 0.0
        self._lock = threading.Lock()

    @property
    def rate(self) -> float:
        return self._rate

    def _reserve(self) -> float:
        with self._lock:
            now = time.monotonic()
            self._tokens = min(self._burst, self._tokens + (now - self._updated) * self._rate)
            self._updated = now
            wait = 0.0
            if now < self._penalty_until:
                wait = self._penalty_until - now
            self._tokens -= 1.0
            if self._tokens < 0.0:
                wait = max(wait, -self._tokens / self._rate)
            return wait

    def penalize(self, seconds: float, *, jitter: float = 0.25) -> None:
        """Pause the bucket after a 429 for \`\`seconds\`\` (+ up to \`\`jitter\`\` x seconds)."""
        with self._lock:
            until = time.monotonic() + seconds * (1.0 + random.random() * jitter)  # noqa: S311  # nosec B311
            self._penalty_until = max(self._penalty_until, until)

    def update_rate(self, rate: float) -> None:
        with self._lock:
            if rate > 0:
                self._rate = rate


class TokenBucket(_TokenBucketState):
    """Blocking token bucket; \`\`acquire\`\` sleeps until a token is available."""

    __slots__ = ()

    def acquire(self) -> float:
        wait = self._reserve()
        if wait > 0.0:
            time.sleep(wait)
        return wait


class AsyncTokenBucket(_TokenBucketState):
    """Same bucket, awaiting instead of sleeping (one event loop)."""

    __slots__ = ()

    async def acquire(self) -> float:
        wait = self._reserve()
        if wait > 0.0:
            await asyncio.sleep(wait)
        return wait


class Throttler:
    """One bucket per operation, seeded from the operation's \`\`RateLimit\`\` (or the client default)."""

    __slots__ = ("_buckets", "_default", "_factory", "_lock")

    def __init__(self, *, default: RateLimit | None = None, factory: type[_TokenBucketState] = TokenBucket) -> None:
        self._buckets: dict[str, _TokenBucketState] = {}
        self._default = default
        self._lock = threading.Lock()
        self._factory = factory

    def bucket(self, key: str, limit: RateLimit | None) -> _TokenBucketState | None:
        b = self._buckets.get(key)
        if b is not None:
            return b
        limit = limit or self._default
        if limit is None:
            return None
        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                b = self._factory(limit)
                self._buckets[key] = b
        return b


# -- per-call options and auth ------------------------------------------------------------


@dataclass(slots=True, frozen=True, kw_only=True)
class RequestOptions:
    """Per-call overrides (\`\`request_options=\`\` on every method)."""

    timeout: httpx2.Timeout | float | None = None
    extra_headers: Mapping[str, str] | None = None
    extra_query: Mapping[str, Any] | None = None
    max_retries: int | None = None
    #: Return the decoded JSON (or the bytes) instead of the model.
    raw: bool = False
    #: Free-form hints for the auth hook (e.g. \`\`{"rdt": ["buyerInfo"]}\`\`).
    auth: Mapping[str, Any] | None = None


class RequestContext:
    """What the auth hook and the throttler know about a call."""

    __slots__ = ("method", "operation", "options", "path", "service")

    def __init__(self, *, operation: str, service: str, method: str, path: str, options: RequestOptions | None) -> None:
        self.operation = operation  # operationId
        self.service = service  # resource module name
        self.method = method
        self.path = path
        self.options = options


class Auth(Protocol):
    def before_request(self, ctx: RequestContext, request: httpx2.Request) -> Mapping[str, str] | None: ...


class AsyncAuth(Protocol):
    def before_request(self, ctx: RequestContext, request: httpx2.Request) -> Awaitable[Mapping[str, str] | None]: ...


class StaticHeaderAuth:
    """Always send the same headers (e.g. an API key); usable sync and async."""

    __slots__ = ("_headers",)

    def __init__(self, headers: Mapping[str, str]) -> None:
        self._headers = dict(headers)

    def before_request(self, ctx: RequestContext, request: httpx2.Request) -> Mapping[str, str]:
        return self._headers


class AsyncStaticHeaderAuth:
    """\`\`StaticHeaderAuth\`\` for the async client."""

    __slots__ = ("_headers",)

    def __init__(self, headers: Mapping[str, str]) -> None:
        self._headers = dict(headers)

    async def before_request(self, ctx: RequestContext, request: httpx2.Request) -> Mapping[str, str]:
        return self._headers


# -- decoding -----------------------------------------------------------------------------

_ADAPTERS: dict[Any, TypeAdapter[Any]] = {}


def _adapter(python_type: Any) -> TypeAdapter[Any]:
    adapter = _ADAPTERS.get(python_type)
    if adapter is None:
        adapter = _ADAPTERS[python_type] = adapter_for(python_type)
    return adapter


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, dt.timestamp() - time.time())


def _encode_json(body: Any) -> bytes:
    if isinstance(body, BaseModel):
        return body.__pydantic_serializer__.to_json(body, by_alias=True, exclude_none=True)
    return to_json(body)


class _BaseHttpClient:
    """Everything that does not perform I/O (shared by the sync and async clients).

    Keyword arguments not listed here (\`\`limits\`\`, \`\`verify\`\`, \`\`proxy\`\`, \`\`http2\`\`, ...)
    go to the httpx2 transport this object creates; pass \`\`transport\`\` or
    \`\`http_client\`\` to bring your own.
    """

    def __init__(
        self,
        *,
        base_url: str,
        auth: Any = None,
        timeout: httpx2.Timeout | float | None = None,
        max_retries: int = MAX_RETRIES,
        retry_statuses: frozenset[int] | set[int] = RETRYABLE_STATUS_CODES,
        throttle: bool = True,
        default_rate_limit: RateLimit | None = None,
        default_headers: Mapping[str, str] | None = None,
        transport: Any = None,
        http_client: Any = None,
        request_id_header: str = REQUEST_ID_HEADER,
        rate_hint_header: str | None = RATE_HINT_HEADER,
        user_agent: str | None = None,
        **httpx_kwargs: Any,
    ) -> None:
        self._options: dict[str, Any] = {
            "base_url": base_url,
            "auth": auth,
            "timeout": timeout,
            "max_retries": max_retries,
            "retry_statuses": retry_statuses,
            "throttle": throttle,
            "default_rate_limit": default_rate_limit,
            "default_headers": default_headers,
            "transport": transport,
            "http_client": http_client,
            "request_id_header": request_id_header,
            "rate_hint_header": rate_hint_header,
            "user_agent": user_agent,
            **httpx_kwargs,
        }
        self._base_url = base_url.rstrip("/")
        self._timeout = httpx2.Timeout(DEFAULT_TIMEOUT if timeout is None else timeout)
        self._max_retries = max_retries
        self._retry_statuses = frozenset(retry_statuses)
        self._auth = auth
        self._throttle_enabled = throttle
        self._default_rate_limit = default_rate_limit
        self._throttler: Throttler | None = None
        self._transport = transport
        self._httpx_kwargs = httpx_kwargs
        self._client: Any = http_client
        self._owns_client = http_client is None
        self._request_id_header = request_id_header
        self._rate_hint_header = rate_hint_header
        self._default_headers: dict[str, str] = {"Accept": "application/json", "User-Agent": user_agent or _user_agent(), **(default_headers or {})}
        self._timeout_extension = self._timeout.as_dict()

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def auth(self) -> Any:
        return self._auth

    @property
    def default_headers(self) -> Mapping[str, str]:
        return self._default_headers

    @property
    def max_retries(self) -> int:
        return self._max_retries

    @property
    def timeout(self) -> httpx2.Timeout:
        return self._timeout

    def with_options(self, **overrides: Any) -> Self:
        """A copy with some constructor options changed, sharing this client's connection pool."""
        options = {**self._options, **overrides}
        if "http_client" not in overrides and "transport" not in overrides:
            options["http_client"] = self._http()
        new = type(self)(**options)
        if options["http_client"] is self._client:
            new._owns_client = False
        if self._throttler is not None and new._throttler is not None and options["default_rate_limit"] == self._default_rate_limit:
            new._throttler = self._throttler
        return new

    def _http(self) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError

    @staticmethod
    def _connection_retries() -> int:
        """Connection-level retries are httpx2's (its transport backs off on connect failures)."""
        return MAX_RETRIES if RETRY_ON_CONNECTION_ERROR else 0

    # -- request building ------------------------------------------------------------------

    def _build(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None,
        headers: Mapping[str, Any] | None,
        json: Any,
        data: Mapping[str, Any] | None,
        files: Any,
        content: bytes | str | None,
        content_type: str | None,
        options: RequestOptions | None,
    ) -> httpx2.Request:
        query = _query(params) if params else []
        if options is not None and options.extra_query:
            query.extend(_query(options.extra_query))
        hdrs: Mapping[str, str] = self._default_headers
        body: bytes | None = None
        if headers or json is not None or content is not None or (options is not None and options.extra_headers):
            merged = {**self._default_headers, **_headers(headers)}
            if options is not None and options.extra_headers:
                merged.update(options.extra_headers)
            if json is not None:
                body = _encode_json(json)
                merged["Content-Type"] = content_type or "application/json"
            elif content is not None:
                body = content.encode() if isinstance(content, str) else content
                merged["Content-Type"] = content_type or "application/octet-stream"
            hdrs = merged
        extensions: dict[str, Any] = {"timeout": self._timeout_extension if options is None or options.timeout is None else httpx2.Timeout(options.timeout).as_dict()}
        if options is not None and options.auth is not None:
            extensions["auth_hints"] = options.auth
        # httpx2 joins the path onto the client's base_url and encodes the URL, the query and the
        # headers; a user-supplied client (as with the OpenAI SDK's http_client=) also contributes
        # its own defaults (headers, cookies, params) and gets the absolute URL since its base_url is its own.
        url = path if self._owns_client else self._base_url + path
        request: httpx2.Request = self._http().build_request(method, url, params=tuple(query) if query else None, headers=hdrs, content=body, data=cast(Any, data), files=files, extensions=extensions)
        return request

    # -- retry policy (status codes; connection retries are httpx2's) ----------------------

    @staticmethod
    def _backoff(attempt: int) -> float:
        delay = min(MAX_DELAY, INITIAL_DELAY * (BACKOFF_MULTIPLIER**attempt))
        return delay * (1.0 + random.random() * JITTER_FACTOR)  # noqa: S311  # nosec B311

    def _retry_delay(self, attempt: int, response: httpx2.Response, bucket: _TokenBucketState | None) -> float:
        retry_after = _parse_retry_after(response.headers.get("retry-after"))
        if retry_after is None and self._rate_hint_header:
            hint = response.headers.get(self._rate_hint_header)
            if hint:
                try:
                    rate = float(hint)
                except ValueError:
                    rate = 0.0
                if rate > 0:
                    retry_after = 1.0 / rate
                    if bucket is not None:
                        bucket.update_rate(rate)
        if retry_after is not None:
            delay = min(max(retry_after, 0.0), MAX_DELAY * 8) * (1.0 + random.random() * 0.25)  # noqa: S311  # nosec B311
        else:
            delay = self._backoff(attempt)
        if response.status_code == 429 and bucket is not None:
            bucket.penalize(delay)
        return delay

    def _bucket(self, key: str, rate_limit: RateLimit | None) -> _TokenBucketState | None:
        throttler = self._throttler
        if throttler is None:
            return None
        return throttler.bucket(key, rate_limit)

    # -- response handling -----------------------------------------------------------------

    def _decode(self, ctx: RequestContext, response: httpx2.Response, python_type: Any, options: RequestOptions | None) -> Any:
        body = response.content
        if options is not None and options.raw:
            if not body:
                return None
            if python_type is bytes:
                return body
            if python_type is str:
                return response.text
            if python_type is not None or "json" in response.headers.get("content-type", ""):
                return from_json(body)
            return body
        if python_type is None:
            return None
        if python_type is bytes:
            return body
        if python_type is str:
            return response.text
        if not body:
            return None
        try:
            return _adapter(python_type).validate_json(body)
        except ValidationError as exc:
            raise APIResponseValidationError(f"{ctx.operation}: response body does not match the spec: {exc}", response=response, cause=exc) from exc

    def _error(self, ctx: RequestContext, response: httpx2.Response, error_type: Any) -> APIStatusError:
        status = response.status_code
        body = response.content
        parsed: Any = None
        if body:
            if error_type is not None:
                try:
                    parsed = _adapter(error_type).validate_json(body)
                except ValidationError:
                    parsed = None
            if parsed is None:
                try:
                    parsed = from_json(body)
                except ValueError:
                    parsed = body
        request_id = response.headers.get(self._request_id_header)
        message = f"{ctx.operation}: HTTP {status} {response.reason_phrase}".rstrip()
        cls = status_error_class(status)
        return cls(message, response=response, body=parsed, request_id=request_id, retry_after=_parse_retry_after(response.headers.get("retry-after")))


class HttpClient(_BaseHttpClient):
    """Synchronous HTTP client over \`\`httpx2.Client\`\` with status retries, throttling and auth."""

    _auth: Auth | None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self._throttle_enabled:
            self._throttler = Throttler(default=self._default_rate_limit)

    def _http(self) -> httpx2.Client:
        client = self._client
        if client is None:
            transport = self._transport or httpx2.HTTPTransport(retries=self._connection_retries(), **self._httpx_kwargs)
            client = httpx2.Client(base_url=self._base_url, transport=transport, timeout=self._timeout)
            self._client = client
        return cast(httpx2.Client, client)

    @property
    def http_client(self) -> httpx2.Client:
        return self._http()

    @property
    def is_closed(self) -> bool:
        return self._client is not None and bool(self._client.is_closed)

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        service: str,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Mapping[str, Any] | None = None,
        files: Any = None,
        content: bytes | str | None = None,
        content_type: str | None = None,
        response: Any = None,
        responses: Mapping[int, Any] | None = None,
        error: Any = None,
        rate_limit: RateLimit | None = None,
        options: RequestOptions | None = None,
    ) -> Any:
        """Send one request; returns the decoded response (\`\`response\`\` type, or per status from \`\`responses\`\`)."""
        ctx = RequestContext(operation=operation, service=service, method=method, path=path, options=options)
        request = self._build(method, path, params=params, headers=headers, json=json, data=data, files=files, content=content, content_type=content_type, options=options)
        client = self._http()
        retries = self._max_retries if options is None or options.max_retries is None else options.max_retries
        bucket = self._bucket(f"{ctx.service}.{ctx.operation}", rate_limit)
        auth = self._auth
        attempt = 0
        while True:
            if bucket is not None:
                cast(TokenBucket, bucket).acquire()
            if auth is not None:
                extra = auth.before_request(ctx, request)
                if extra:
                    request.headers.update(extra)
            try:
                resp = client.send(request)
            except httpx2.TimeoutException as exc:
                if not RETRY_ON_TIMEOUT or attempt >= retries:
                    raise APITimeoutError(request=request, cause=exc) from exc
                delay = self._backoff(attempt)
                log.debug("%s: timeout (%s); retry %d/%d in %.2fs", ctx.operation, exc, attempt + 1, retries, delay)
                time.sleep(delay)
                attempt += 1
                continue
            except httpx2.TransportError as exc:
                raise APIConnectionError(str(exc) or "Connection error.", request=request, cause=exc) from exc
            status = resp.status_code
            if status < 400:
                break
            if status in self._retry_statuses and attempt < retries:
                delay = self._retry_delay(attempt, resp, bucket)
                resp.close()
                log.debug("%s: HTTP %d; retry %d/%d in %.2fs", ctx.operation, status, attempt + 1, retries, delay)
                time.sleep(delay)
                attempt += 1
                continue
            raise self._error(ctx, resp, error)
        python_type = responses.get(status, response) if responses else response
        return self._decode(ctx, resp, python_type, options)


class AsyncHttpClient(_BaseHttpClient):
    """Asynchronous HTTP client over \`\`httpx2.AsyncClient\`\` (\`\`httpx_aiohttp\`\` transport when installed)."""

    _auth: AsyncAuth | None

    def __init__(self, *, prefer_aiohttp: bool = True, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._options["prefer_aiohttp"] = prefer_aiohttp
        self._prefer_aiohttp = prefer_aiohttp
        if self._throttle_enabled:
            self._throttler = Throttler(default=self._default_rate_limit, factory=AsyncTokenBucket)

    def _http(self) -> httpx2.AsyncClient:
        client = self._client
        if client is None:
            transport = self._transport or async_transport(retries=self._connection_retries(), prefer_aiohttp=self._prefer_aiohttp, **self._httpx_kwargs)
            client = httpx2.AsyncClient(base_url=self._base_url, transport=transport, timeout=self._timeout)
            self._client = client
        return cast(httpx2.AsyncClient, client)

    @property
    def http_client(self) -> httpx2.AsyncClient:
        return self._http()

    @property
    def is_closed(self) -> bool:
        return self._client is not None and bool(self._client.is_closed)

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        await self.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        service: str,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, Any] | None = None,
        json: Any = None,
        data: Mapping[str, Any] | None = None,
        files: Any = None,
        content: bytes | str | None = None,
        content_type: str | None = None,
        response: Any = None,
        responses: Mapping[int, Any] | None = None,
        error: Any = None,
        rate_limit: RateLimit | None = None,
        options: RequestOptions | None = None,
    ) -> Any:
        ctx = RequestContext(operation=operation, service=service, method=method, path=path, options=options)
        request = self._build(method, path, params=params, headers=headers, json=json, data=data, files=files, content=content, content_type=content_type, options=options)
        client = self._http()
        retries = self._max_retries if options is None or options.max_retries is None else options.max_retries
        bucket = self._bucket(f"{ctx.service}.{ctx.operation}", rate_limit)
        auth = self._auth
        attempt = 0
        while True:
            if bucket is not None:
                await cast(AsyncTokenBucket, bucket).acquire()
            if auth is not None:
                extra = await auth.before_request(ctx, request)
                if extra:
                    request.headers.update(extra)
            try:
                resp = await client.send(request)
            except httpx2.TimeoutException as exc:
                if not RETRY_ON_TIMEOUT or attempt >= retries:
                    raise APITimeoutError(request=request, cause=exc) from exc
                delay = self._backoff(attempt)
                log.debug("%s: timeout (%s); retry %d/%d in %.2fs", ctx.operation, exc, attempt + 1, retries, delay)
                await asyncio.sleep(delay)
                attempt += 1
                continue
            except httpx2.TransportError as exc:
                raise APIConnectionError(str(exc) or "Connection error.", request=request, cause=exc) from exc
            status = resp.status_code
            if status < 400:
                break
            if status in self._retry_statuses and attempt < retries:
                delay = self._retry_delay(attempt, resp, bucket)
                await resp.aclose()
                log.debug("%s: HTTP %d; retry %d/%d in %.2fs", ctx.operation, status, attempt + 1, retries, delay)
                await asyncio.sleep(delay)
                attempt += 1
                continue
            raise self._error(ctx, resp, error)
        python_type = responses.get(status, response) if responses else response
        return self._decode(ctx, resp, python_type, options)


# -- pagination ---------------------------------------------------------------------------


def _walk(obj: Any, path: tuple[str, ...]) -> Any:
    current: Any = obj
    for name in path:
        if current is None:
            return None
        if isinstance(current, Mapping):
            current = cast(Mapping[str, Any], current).get(name)
        else:
            current = getattr(current, name, None)
    return current


def _next_kwargs(kwargs: Mapping[str, Any], token_param: str, token: Any, drop: bool, keep: tuple[str, ...]) -> dict[str, Any]:
    """Arguments of the next page: the token, plus (unless the API wants them dropped) the original arguments.

    Dropped arguments are passed as \`\`None\`\` so required parameters stay
    satisfied; \`\`None\`\` never reaches the wire.
    """
    if not drop:
        return {**kwargs, token_param: token}
    out = {k: (v if k in keep or k == "request_options" else None) for k, v in kwargs.items()}
    out[token_param] = token
    return out


def paginate(
    fn: Callable[..., Any],
    kwargs: Mapping[str, Any],
    *,
    items: tuple[str, ...],
    token: tuple[str, ...],
    token_param: str,
    wire_items: tuple[str, ...] = (),
    wire_token: tuple[str, ...] = (),
    drop_params_on_next: bool = False,
    keep_params: tuple[str, ...] = (),
    single: bool = False,
) -> Iterator[Any]:
    """Call \`\`fn(**kwargs)\`\` page after page, yielding the items of every page.

    \`\`items\`\` / \`\`token\`\` are attribute paths on the decoded response (the
    \`\`wire_*\`\` paths apply to raw responses); \`\`single\`\` yields the container
    itself instead of iterating it.
    """
    current: dict[str, Any] = dict(kwargs)
    raw = bool(getattr(current.get("request_options"), "raw", False))
    while True:
        page = fn(**current)
        found = _walk(page, wire_items if raw else items)
        if single:
            if found is not None:
                yield found
        elif found:
            yield from found
        next_token = _walk(page, wire_token if raw else token)
        if not next_token:
            return
        current = _next_kwargs(current, token_param, next_token, drop_params_on_next, keep_params)


async def apaginate(
    fn: Callable[..., Awaitable[Any]],
    kwargs: Mapping[str, Any],
    *,
    items: tuple[str, ...],
    token: tuple[str, ...],
    token_param: str,
    wire_items: tuple[str, ...] = (),
    wire_token: tuple[str, ...] = (),
    drop_params_on_next: bool = False,
    keep_params: tuple[str, ...] = (),
    single: bool = False,
) -> AsyncIterator[Any]:
    current: dict[str, Any] = dict(kwargs)
    raw = bool(getattr(current.get("request_options"), "raw", False))
    while True:
        page = await fn(**current)
        found = _walk(page, wire_items if raw else items)
        if single:
            if found is not None:
                yield found
        elif found:
            for item in found:
                yield item
        next_token = _walk(page, wire_token if raw else token)
        if not next_token:
            return
        current = _next_kwargs(current, token_param, next_token, drop_params_on_next, keep_params)


# -- transports ---------------------------------------------------------------------------


def aiohttp_available() -> bool:
    return importlib.util.find_spec("httpx_aiohttp") is not None


def async_transport(*, retries: int = 0, prefer_aiohttp: bool = True, **kwargs: Any) -> httpx2.AsyncBaseTransport:
    """\`\`httpx_aiohttp.AiohttpTransport\`\` when the \`\`aiohttp\`\` extra is installed, else \`\`httpx2.AsyncHTTPTransport\`\`."""
    if prefer_aiohttp:
        try:
            import httpx_aiohttp.transport as _hat
        except ImportError:
            pass
        else:
            hx: Any = getattr(_hat, "httpx")  # noqa: B009 - the httpx module httpx_aiohttp was written against
            limits = kwargs.get("limits")
            hx_limits = hx.Limits(max_connections=limits.max_connections, max_keepalive_connections=limits.max_keepalive_connections, keepalive_expiry=limits.keepalive_expiry) if limits is not None else hx.Limits()
            inner: Any = _hat.AiohttpTransport(limits=hx_limits, verify=kwargs.get("verify", True))
            if hx is httpx2:  # alias_httpx() was called
                return cast(httpx2.AsyncBaseTransport, inner)
            return _HttpxBridgeTransport(inner, hx)
    return httpx2.AsyncHTTPTransport(retries=retries, **kwargs)


class _BridgedStream(httpx2.AsyncByteStream):
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._inner:
            yield chunk

    async def aclose(self) -> None:
        aclose = getattr(self._inner, "aclose", None)
        if aclose is not None:
            await aclose()


class _HttpxBridgeTransport(httpx2.AsyncBaseTransport):
    """Adapts a transport written for \`\`httpx\`\` to \`\`httpx2\`\`'s interface."""

    def __init__(self, inner: Any, httpx_mod: Any) -> None:
        self._inner = inner
        self._httpx = httpx_mod

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        hx = self._httpx
        old_req = hx.Request(request.method, str(request.url), headers=request.headers.raw, stream=_BridgedStream(request.stream), extensions=dict(request.extensions))  # type: ignore[arg-type]
        old_resp = await self._inner.handle_async_request(old_req)
        return httpx2.Response(status_code=old_resp.status_code, headers=old_resp.headers.raw, stream=_BridgedStream(old_resp.stream), extensions=dict(old_resp.extensions))

    async def aclose(self) -> None:
        await self._inner.aclose()


__all__ = [
    "DEFAULT_TIMEOUT",
    "MAX_RETRIES",
    "RETRYABLE_STATUS_CODES",
    "AsyncAuth",
    "AsyncHttpClient",
    "AsyncStaticHeaderAuth",
    "AsyncTokenBucket",
    "Auth",
    "HttpClient",
    "RateLimit",
    "RequestContext",
    "RequestOptions",
    "StaticHeaderAuth",
    "Throttler",
    "TokenBucket",
    "aiohttp_available",
    "apaginate",
    "async_transport",
    "joined",
    "paginate",
    "path_segment",
    "scalar",
]
`;
}
