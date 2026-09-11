"""Amazon Selling Partner API for Python.

A spec-generated client: ``codegen/`` (built on oagen) turns the pinned Amazon
Swagger models into typed pydantic models and resource classes, and every
operation is a method on ``SellingPartner`` (sync) and ``AsyncSellingPartner``
(async). Importing this package builds no schemas; an API's modules are
imported on first attribute access (``client.orders.v0``).

The generic core (``runtime``, ``Client`` / ``AsyncClient``) is API-agnostic;
everything Amazon-specific lives in ``plugins.amazon_spapi``. The ``client``,
``reports``, ``vendor`` and ``utils`` subpackages keep the 0.1.x entry points
working (see ``MIGRATION.md``).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

try:
    __version__ = version("amzn-selling-partner")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0"

# 0.1.x compatibility subpackages (they import the plugin eagerly, so they come last)
from . import client, reports, utils, vendor  # noqa: E402
from .runtime._errors import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
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

if TYPE_CHECKING:
    from ._client import AsyncClient, Client
    from .plugins.amazon_spapi import AsyncSellingPartner, SellingPartner

__all__ = [
    "NOT_GIVEN",
    "APIConnectionError",
    "APIError",
    "APIResponseValidationError",
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
    "client",
    "reports",
    "utils",
    "vendor",
]

_LAZY = {
    "Client": "._client",
    "AsyncClient": "._client",
    "SellingPartner": ".plugins.amazon_spapi",
    "AsyncSellingPartner": ".plugins.amazon_spapi",
}


def __getattr__(name: str) -> Any:
    module = _LAZY.get(name)
    if module is None:
        raise AttributeError(f"module 'amzn_selling_partner' has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(module, __name__), name)
