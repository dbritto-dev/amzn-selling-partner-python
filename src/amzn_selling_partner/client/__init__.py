import os
import warnings

from .._regions import SellingPartnerRegion

__all__ = ["SellingPartnerRegion", "BaseClient"]


class BaseClient:
    """Deprecated. Use `amzn_selling_partner.Client` or `amzn_selling_partner.AsyncClient`.

    Only the pure string-building endpoint helpers survive here; `.http_session` and the
    `requests`-based auth machinery that used to live in `client.auth` are gone (see
    MIGRATION.md) since they were never part of this class's tested public contract beyond
    those helpers.
    """

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
    ) -> None:
        warnings.warn(
            "amzn_selling_partner.client.BaseClient is deprecated; use "
            "amzn_selling_partner.Client or amzn_selling_partner.AsyncClient instead. "
            "See MIGRATION.md.",
            DeprecationWarning,
            stacklevel=2,
        )
        self.region = selling_partner_region
        self.sandbox = sandbox

    def get_api_endpoint(self) -> str:
        return self.region.api_endpoint if not self.sandbox else self.region.api_sandbox_endpoint

    def get_resource_path(self) -> str:
        raise NotImplementedError()

    def get_resource_endpoint(self) -> str:
        return f"{self.get_api_endpoint()}/{self.get_resource_path()}"

    def get_operation_endpoint(self, operation_method: str) -> str:
        return f"{self.get_resource_endpoint()}/{operation_method}"
