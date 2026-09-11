/** `errors.py`: the exception hierarchy, status classes from the spec's error policy (`ctx.spec.sdk.errors`). */
import type { EmitterContext, GeneratedFile } from '@workos/oagen';
import { HEADER_DOC, file } from './header.js';
import { optionsOf } from './options.js';

export function errorClassName(kind: string): string {
  return kind.endsWith('Error') ? kind : `${kind}Error`;
}

export function renderErrorsModule(ctx: EmitterContext): string {
  const policy = optionsOf(ctx).sdk.errors;
  const server = errorClassName(policy.serverErrorKind);
  const entries = Object.entries(policy.statusCodeMap)
    .map(([code, kind]) => [Number(code), errorClassName(kind)] as const)
    .sort((a, b) => a[0] - b[0]);
  const classes = [...new Set(entries.map(([, cls]) => cls))];
  const out: string[] = [];
  out.push(`"""Exceptions raised by the ${ctx.spec.name} client.

\`\`APIError\`\` is the base; transport problems become \`\`APIConnectionError\`\` /
\`\`APITimeoutError\`\` and non-2xx responses become \`\`APIStatusError\`\` or one of
its status-specific subclasses (\`\`STATUS_ERRORS\`\`). \`\`APIStatusError.body\`\`
holds the decoded error payload when the spec's error schema validated,
otherwise the raw JSON (or the bytes when the body is not JSON).

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
  out.push('STATUS_ERRORS: dict[int, type[APIStatusError]] = {');
  for (const [code, cls] of entries) out.push(`    ${code}: ${cls},`);
  out.push('}', '', '');
  out.push('def status_error_class(status_code: int) -> type[APIStatusError]:');
  out.push('    cls = STATUS_ERRORS.get(status_code)');
  out.push('    if cls is not None:');
  out.push('        return cls');
  out.push(`    if status_code >= 500:`);
  out.push(`        return ${server}`);
  out.push('    return APIStatusError', '', '');
  const all = ['APIConnectionError', 'APIError', 'APIResponseValidationError', 'APIStatusError', 'APITimeoutError', 'STATUS_ERRORS', ...classes, server, 'status_error_class'].sort();
  out.push('__all__ = [', ...all.map((n) => `    "${n}",`), ']', '');
  return out.join('\n');
}

export function generateErrors(ctx: EmitterContext): GeneratedFile[] {
  return [file('errors.py', renderErrorsModule(ctx))];
}
