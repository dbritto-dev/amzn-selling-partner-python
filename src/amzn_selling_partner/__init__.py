"""
Amazon Selling Partner API for Python
"""

from importlib.metadata import version

from . import client, reports, utils, vendor
from ._client import AsyncClient, Client
from ._regions import SellingPartnerRegion

__version__ = version("amzn-selling-partner")

__all__ = [
    "AsyncClient",
    "Client",
    "SellingPartnerRegion",
    "client",
    "reports",
    "utils",
    "vendor",
]
