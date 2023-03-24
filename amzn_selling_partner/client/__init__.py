import enum
import os

import requests

from amzn_selling_partner.client.auth import ClientSessionAuth


class SellingPartnerRegion(tuple, enum.Enum):
    NORTH_AMERICA = (
        "https://sellingpartnerapi-na.amazon.com",
        "https://sandbox.sellingpartnerapi-na.amazon.com",
        "us-east-1",
    )
    EUROPE = (
        "https://sellingpartnerapi-eu.amazon.com",
        "https://sandbox.sellingpartnerapi-eu.amazon.com",
        "eu-west-1",
    )
    FAR_EAST = (
        "https://sellingpartnerapi-fe.amazon.com",
        "https://sandbox.sellingpartnerapi-fe.amazon.com",
        "us-west-2",
    )

    @property
    def api_endpoint(self):
        return self.value[0]

    @property
    def api_sandbox_endpoint(self):
        return self.value[1]

    @property
    def region_name(self):
        return self.value[2]


class BaseClient:
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
        self.region = selling_partner_region
        self.sandbox = sandbox
        self.http_session = requests.Session()
        self.http_session.auth = ClientSessionAuth(
            selling_partner_app_client_id=selling_partner_app_client_id,
            selling_partner_app_client_secret=selling_partner_app_client_secret,
            selling_partner_app_refresh_token=selling_partner_app_refresh_token,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_region=selling_partner_region.region_name,
            aws_selling_partner_role=aws_selling_partner_role,
            aws_selling_partner_role_session_name=aws_selling_partner_role_session_name,
        )

    def get_api_endpoint(self) -> str:
        return self.region.api_endpoint if not self.sandbox else self.region.api_sandbox_endpoint

    def get_resource_path(self) -> str:
        raise NotImplementedError()

    def get_resource_endpoint(self) -> str:
        return f"{self.get_api_endpoint()}/{self.get_resource_path()}"

    def get_operation_endpoint(self, operation_method: str) -> str:
        return f"{self.get_resource_endpoint()}/{operation_method}"
