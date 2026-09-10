"""Hand-written, API-agnostic runtime: clients, errors, pagination, auth, throttling."""

from ._auth import AsyncAuthHook, AsyncNoAuth, AuthHook, NoAuth, StaticHeaderAuth
from ._errors import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)
from ._json import JsonCodec, PydanticJsonCodec, StdlibJsonCodec
from ._pagination import AsyncPage, Pagination, SyncPage
from ._stream import AsyncStream, ServerSentEvent, Stream
from ._throttle import AsyncThrottler, AsyncTokenBucket, RateLimit, Throttler, TokenBucket
from ._types import NOT_GIVEN, NotGiven, RequestOptions

__all__ = [
    "NOT_GIVEN",
    "APIConnectionError",
    "APIError",
    "APIStatusError",
    "APITimeoutError",
    "AsyncAuthHook",
    "AsyncNoAuth",
    "AsyncPage",
    "AsyncStream",
    "AsyncThrottler",
    "AsyncTokenBucket",
    "AuthHook",
    "AuthenticationError",
    "JsonCodec",
    "NoAuth",
    "NotGiven",
    "Pagination",
    "PydanticJsonCodec",
    "RateLimit",
    "RateLimitError",
    "RequestOptions",
    "ServerSentEvent",
    "StaticHeaderAuth",
    "StdlibJsonCodec",
    "Stream",
    "SyncPage",
    "Throttler",
    "TokenBucket",
]
