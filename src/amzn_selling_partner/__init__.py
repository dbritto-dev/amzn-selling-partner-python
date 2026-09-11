"""
Amazon Selling Partner API for Python (compatibility package).

The implementation moved to :mod:`spapi`. This package keeps the public entry
points of the 0.1.x releases working on top of the new runtime; see
``MIGRATION.md`` for the differences.
"""

from importlib.metadata import PackageNotFoundError, version

from . import client, reports, utils, vendor

try:
    __version__ = version("amzn-selling-partner")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = ["client", "reports", "utils", "vendor"]
