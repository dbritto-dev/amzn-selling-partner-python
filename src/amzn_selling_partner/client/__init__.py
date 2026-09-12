"""Compatibility ``BaseClient`` / ``SellingPartnerRegion``.

``BaseClient`` wraps :class:`amzn_selling_partner.SellingPartner`. The AWS keyword arguments
of the old constructor are accepted and ignored (the Selling Partner API no
longer requires AWS Signature V4).
"""

from __future__ import annotations

import os
import warnings
from typing import Any

from ..plugins.amazon_spapi import Region, SellingPartner
from . import auth

#: Same members as before (``NORTH_AMERICA`` / ``EUROPE`` / ``FAR_EAST``) with
#: ``api_endpoint``, ``api_sandbox_endpoint`` and ``region_name`` properties.
SellingPartnerRegion = Region


class BaseClient:
    """Old-style client: one instance per API resource.

    ``sp`` is the underlying :class:`amzn_selling_partner.SellingPartner`; subclasses map
    their old methods onto it.
    """

    def __init__(
        self,
        *,
        selling_partner_region: Region = Region.NORTH_AMERICA,
        selling_partner_app_client_id: str | None = None,
        selling_partner_app_client_secret: str | None = None,
        selling_partner_app_refresh_token: str | None = None,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        aws_selling_partner_role: str | None = None,
        aws_selling_partner_role_session_name: str | None = None,
        sandbox: bool = False,
        **options: Any,
    ) -> None:
        if any((aws_access_key_id, aws_secret_access_key, aws_selling_partner_role, aws_selling_partner_role_session_name)):
            warnings.warn(
                "AWS credentials are no longer used by the Selling Partner API; the aws_* arguments are ignored",
                DeprecationWarning,
                stacklevel=2,
            )
        self.region = selling_partner_region
        self.sandbox = sandbox
        client_id = selling_partner_app_client_id or os.getenv("SELLING_PARTNER_APP_CLIENT_ID")
        client_secret = selling_partner_app_client_secret or os.getenv("SELLING_PARTNER_APP_CLIENT_SECRET")
        refresh_token = selling_partner_app_refresh_token or os.getenv("SELLING_PARTNER_APP_REFRESH_TOKEN")
        self.sp = SellingPartner(
            region=selling_partner_region,
            sandbox=sandbox,
            client_id=client_id or None,
            client_secret=client_secret or None,
            refresh_token=refresh_token or None,
            **options,
        )

    def get_api_endpoint(self) -> str:
        return self.region.api_sandbox_endpoint if self.sandbox else self.region.api_endpoint

    def get_resource_path(self) -> str:
        raise NotImplementedError()

    def get_resource_endpoint(self) -> str:
        return f"{self.get_api_endpoint()}/{self.get_resource_path()}"

    def get_operation_endpoint(self, operation_method: str) -> str:
        return f"{self.get_resource_endpoint()}/{operation_method}"

    def close(self) -> None:
        self.sp.close()


__all__ = ["BaseClient", "SellingPartnerRegion", "auth"]
