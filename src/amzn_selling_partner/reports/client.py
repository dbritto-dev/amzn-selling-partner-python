import os
import warnings

from .. import _client
from .._regions import SellingPartnerRegion
from . import _sync


class Client(_sync.Reports):
    """Deprecated. Use `amzn_selling_partner.Client(...).reports` instead."""

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
            "amzn_selling_partner.reports.Client is deprecated; use "
            "amzn_selling_partner.Client(...).reports instead. See MIGRATION.md.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._new_client = _client.Client(
            selling_partner_region=selling_partner_region,
            selling_partner_app_client_id=selling_partner_app_client_id,
            selling_partner_app_client_secret=selling_partner_app_client_secret,
            selling_partner_app_refresh_token=selling_partner_app_refresh_token,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_selling_partner_role=aws_selling_partner_role,
            aws_selling_partner_role_session_name=aws_selling_partner_role_session_name,
            sandbox=sandbox,
        )
        super().__init__(self._new_client)

    def get_resource_path(self) -> str:
        return _sync._RESOURCE_PATH

    def get_resource_endpoint(self) -> str:
        return f"{self._new_client.base_url}/{self.get_resource_path()}"

    def get_operation_endpoint(self, operation_method: str) -> str:
        return f"{self.get_resource_endpoint()}/{operation_method}"
