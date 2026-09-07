"""
Amazon Selling Partner API for Python
"""

from importlib.metadata import version

from . import client, reports, utils, vendor
from ._client import AsyncClient, Client
from ._regions import SellingPartnerRegion
from ._transports import DefaultAioHttpClient, DefaultAsyncHttpxClient, DefaultHttpxClient

__version__ = version("amzn-selling-partner")

__all__ = [
    "AsyncClient",
    "Client",
    "SellingPartnerRegion",
    "DefaultHttpxClient",
    "DefaultAsyncHttpxClient",
    "DefaultAioHttpClient",
    "client",
    "reports",
    "utils",
    "vendor",
]
