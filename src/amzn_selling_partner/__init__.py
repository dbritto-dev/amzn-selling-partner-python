"""
Amazon Selling Partner API for Python
"""

from importlib.metadata import version

from . import client, reports, utils, vendor

__version__ = version("amzn-selling-partner")

__all__ = ["client", "reports", "utils", "vendor"]
