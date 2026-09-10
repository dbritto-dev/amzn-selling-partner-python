"""Exception hierarchy raised by the runtime.

``APIError`` is the base; transport problems become ``APIConnectionError`` /
``APITimeoutError`` and non-2xx responses become ``APIStatusError`` (or one of
its status-specific subclasses). ``APIStatusError.body`` holds the decoded error
payload when the spec's error schema validated, otherwise the raw JSON (or the
bytes when the body is not JSON).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx2


class APIError(Exception):
    """Base class for every error raised by a client."""

    message: str
    request: httpx2.Request | None

    def __init__(self, message: str, *, request: httpx2.Request | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.request = request


class APIConnectionError(APIError):
    """The request never produced a response (DNS, TLS, connection reset, ...)."""

    def __init__(
        self,
        message: str = "Connection error.",
        *,
        request: httpx2.Request | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message, request=request)
        self.__cause__ = cause


class APITimeoutError(APIConnectionError):
    """The request timed out (connect, read, write or pool timeout)."""

    def __init__(
        self,
        message: str = "Request timed out.",
        *,
        request: httpx2.Request | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message, request=request, cause=cause)


class APIStatusError(APIError):
    """A response with a non-success status code."""

    status_code: int
    response: httpx2.Response
    body: Any
    request_id: str | None

    def __init__(
        self,
        message: str,
        *,
        response: httpx2.Response,
        body: Any,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message, request=response.request)
        self.status_code = response.status_code
        self.response = response
        self.body = body
        self.request_id = request_id

    def __str__(self) -> str:
        rid = f" (request id: {self.request_id})" if self.request_id else ""
        return f"{self.message}{rid}"


class BadRequestError(APIStatusError):
    pass


class AuthenticationError(APIStatusError):
    """401 or 403."""


class NotFoundError(APIStatusError):
    pass


class ConflictError(APIStatusError):
    pass


class UnprocessableEntityError(APIStatusError):
    pass


class RateLimitError(APIStatusError):
    """429. ``retry_after`` is the server-suggested delay in seconds, if any."""

    retry_after: float | None

    def __init__(
        self,
        message: str,
        *,
        response: httpx2.Response,
        body: Any,
        request_id: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, response=response, body=body, request_id=request_id)
        self.retry_after = retry_after


class InternalServerError(APIStatusError):
    """Any 5xx."""


_STATUS_CLASSES: dict[int, type[APIStatusError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: AuthenticationError,
    404: NotFoundError,
    409: ConflictError,
    422: UnprocessableEntityError,
    429: RateLimitError,
}


def status_error_class(status_code: int) -> type[APIStatusError]:
    cls = _STATUS_CLASSES.get(status_code)
    if cls is not None:
        return cls
    if status_code >= 500:
        return InternalServerError
    return APIStatusError
