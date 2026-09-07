import os
import typing

import httpx2

from . import _auth, _base_client
from ._regions import SellingPartnerRegion
from .reports._async import AsyncReports
from .reports._sync import Reports
from .vendor.orders._async import AsyncOrders
from .vendor.orders._sync import Orders

__all__ = ["SellingPartnerRegion", "Client", "AsyncClient"]


def _base_url(region: SellingPartnerRegion, sandbox: bool) -> str:
    return region.api_endpoint if not sandbox else region.api_sandbox_endpoint


def _build_auth(
    *,
    selling_partner_region: SellingPartnerRegion,
    selling_partner_app_client_id: str,
    selling_partner_app_client_secret: str,
    selling_partner_app_refresh_token: str,
    aws_access_key_id: str,
    aws_secret_access_key: str,
    aws_selling_partner_role: str,
    aws_selling_partner_role_session_name: str,
) -> _auth.SPAPIAuth:
    return _auth.SPAPIAuth(
        selling_partner_app_client_id=selling_partner_app_client_id,
        selling_partner_app_client_secret=selling_partner_app_client_secret,
        selling_partner_app_refresh_token=selling_partner_app_refresh_token,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        aws_region=selling_partner_region.region_name,
        aws_selling_partner_role=aws_selling_partner_role,
        aws_selling_partner_role_session_name=aws_selling_partner_role_session_name,
    )


class _Vendor:
    def __init__(self, client: "Client") -> None:
        self.orders = Orders(client)


class _AsyncVendor:
    def __init__(self, client: "AsyncClient") -> None:
        self.orders = AsyncOrders(client)


class Client(_base_client.SyncAPIClient):
    def __init__(
        self,
        *,
        selling_partner_region: SellingPartnerRegion = SellingPartnerRegion.NORTH_AMERICA,
        selling_partner_app_client_id: str = os.getenv("SELLING_PARTNER_APP_CLIENT_ID", ""),
        selling_partner_app_client_secret: str = os.getenv(
            "SELLING_PARTNER_APP_CLIENT_SECRET", ""
        ),
        selling_partner_app_refresh_token: str = os.getenv(
            "SELLING_PARTNER_APP_REFRESH_TOKEN", ""
        ),
        aws_access_key_id: str = os.getenv("AWS_ACCESS_KEY_ID", ""),
        aws_secret_access_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        aws_selling_partner_role: str = os.getenv("AWS_SELLING_PARTNER_ROLE", ""),
        aws_selling_partner_role_session_name: str = os.getenv(
            "AWS_SELLING_PARTNER_ROLE_SESSION_NAME", ""
        ),
        sandbox: bool = False,
        timeout: float = _base_client.DEFAULT_TIMEOUT,
        max_retries: int = _base_client.DEFAULT_MAX_RETRIES,
        http_client: typing.Optional[httpx2.Client] = None,
        transport: typing.Optional[httpx2.BaseTransport] = None,
        limits: typing.Optional[httpx2.Limits] = None,
    ) -> None:
        self.region = selling_partner_region
        self.sandbox = sandbox
        super().__init__(
            base_url=_base_url(selling_partner_region, sandbox),
            auth=_build_auth(
                selling_partner_region=selling_partner_region,
                selling_partner_app_client_id=selling_partner_app_client_id,
                selling_partner_app_client_secret=selling_partner_app_client_secret,
                selling_partner_app_refresh_token=selling_partner_app_refresh_token,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                aws_selling_partner_role=aws_selling_partner_role,
                aws_selling_partner_role_session_name=aws_selling_partner_role_session_name,
            ),
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
            transport=transport,
            limits=limits,
        )
        self.reports = Reports(self)
        self.vendor = _Vendor(self)


class AsyncClient(_base_client.AsyncAPIClient):
    def __init__(
        self,
        *,
        selling_partner_region: SellingPartnerRegion = SellingPartnerRegion.NORTH_AMERICA,
        selling_partner_app_client_id: str = os.getenv("SELLING_PARTNER_APP_CLIENT_ID", ""),
        selling_partner_app_client_secret: str = os.getenv(
            "SELLING_PARTNER_APP_CLIENT_SECRET", ""
        ),
        selling_partner_app_refresh_token: str = os.getenv(
            "SELLING_PARTNER_APP_REFRESH_TOKEN", ""
        ),
        aws_access_key_id: str = os.getenv("AWS_ACCESS_KEY_ID", ""),
        aws_secret_access_key: str = os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        aws_selling_partner_role: str = os.getenv("AWS_SELLING_PARTNER_ROLE", ""),
        aws_selling_partner_role_session_name: str = os.getenv(
            "AWS_SELLING_PARTNER_ROLE_SESSION_NAME", ""
        ),
        sandbox: bool = False,
        timeout: float = _base_client.DEFAULT_TIMEOUT,
        max_retries: int = _base_client.DEFAULT_MAX_RETRIES,
        http_client: typing.Optional[httpx2.AsyncClient] = None,
        transport: typing.Optional[httpx2.AsyncBaseTransport] = None,
        limits: typing.Optional[httpx2.Limits] = None,
    ) -> None:
        self.region = selling_partner_region
        self.sandbox = sandbox
        super().__init__(
            base_url=_base_url(selling_partner_region, sandbox),
            auth=_build_auth(
                selling_partner_region=selling_partner_region,
                selling_partner_app_client_id=selling_partner_app_client_id,
                selling_partner_app_client_secret=selling_partner_app_client_secret,
                selling_partner_app_refresh_token=selling_partner_app_refresh_token,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                aws_selling_partner_role=aws_selling_partner_role,
                aws_selling_partner_role_session_name=aws_selling_partner_role_session_name,
            ),
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
            transport=transport,
            limits=limits,
        )
        self.reports = AsyncReports(self)
        self.vendor = _AsyncVendor(self)
