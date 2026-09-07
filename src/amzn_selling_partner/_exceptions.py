import typing

import httpx2

__all__ = [
    "SPAPIError",
    "SPAPIAuthError",
    "APIConnectionError",
    "APITimeoutError",
    "APIStatusError",
    "BadRequestError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "UnprocessableEntityError",
    "RateLimitError",
    "InternalServerError",
]


class SPAPIError(Exception):
    """Root of every exception raised by this SDK's own code."""


class SPAPIAuthError(SPAPIError):
    """Raised when the LWA token refresh or AWS STS credential refresh fails."""

    def __init__(self, *args: object, cause: typing.Optional[Exception] = None) -> None:
        super().__init__(*args)
        self.cause = cause


class APIConnectionError(SPAPIError):
    def __init__(self, *, request: httpx2.Request, message: str = "Connection error.") -> None:
        super().__init__(message)
        self.request = request


class APITimeoutError(APIConnectionError):
    def __init__(self, *, request: httpx2.Request) -> None:
        super().__init__(request=request, message="Request timed out.")


class APIStatusError(SPAPIError):
    def __init__(self, message: str, *, response: httpx2.Response, body: object) -> None:
        super().__init__(message)
        self.response = response
        self.status_code = response.status_code
        self.body = body


class BadRequestError(APIStatusError):
    pass


class AuthenticationError(APIStatusError):
    pass


class PermissionDeniedError(APIStatusError):
    pass


class NotFoundError(APIStatusError):
    pass


class ConflictError(APIStatusError):
    pass


class UnprocessableEntityError(APIStatusError):
    pass


class RateLimitError(APIStatusError):
    pass


class InternalServerError(APIStatusError):
    pass


_SERVER_ERROR_THRESHOLD = 500

_STATUS_TO_EXCEPTION: typing.Dict[int, typing.Type[APIStatusError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: UnprocessableEntityError,
    429: RateLimitError,
}


def status_to_exception(status_code: int) -> typing.Type[APIStatusError]:
    if status_code in _STATUS_TO_EXCEPTION:
        return _STATUS_TO_EXCEPTION[status_code]
    if status_code >= _SERVER_ERROR_THRESHOLD:
        return InternalServerError
    return APIStatusError
