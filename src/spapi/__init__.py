"""spapi: a spec-driven HTTP client library (Amazon Selling Partner API bundled).

Importing this package builds no models; APIs are loaded and compiled lazily on
first attribute access (``client.orders.v0``).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

from .runtime._errors import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    RateLimitError,
    UnprocessableEntityError,
)
from .runtime._pagination import AsyncPage, Pagination, SyncPage
from .runtime._types import NOT_GIVEN, NotGiven, RequestOptions

try:
    __version__ = version("amzn-selling-partner")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0"

if TYPE_CHECKING:
    from .client import AsyncClient, AsyncSellingPartner, Client, SellingPartner

__all__ = [
    "NOT_GIVEN",
    "APIConnectionError",
    "APIError",
    "APIStatusError",
    "APITimeoutError",
    "AsyncClient",
    "AsyncPage",
    "AsyncSellingPartner",
    "AuthenticationError",
    "BadRequestError",
    "Client",
    "ConflictError",
    "InternalServerError",
    "NotFoundError",
    "NotGiven",
    "Pagination",
    "RateLimitError",
    "RequestOptions",
    "SellingPartner",
    "SyncPage",
    "UnprocessableEntityError",
    "__version__",
]

_LAZY = {
    "Client": ".client",
    "AsyncClient": ".client",
    "SellingPartner": ".client",
    "AsyncSellingPartner": ".client",
}


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module 'spapi' has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(module, __name__), name)
