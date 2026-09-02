import datetime
import platform
import typing

import boto3
import botocore.credentials
import requests
import requests_aws4auth


class ClientSessionAuthTemporaryCredentialsError(Exception):
    def __init__(self, *args, cause: typing.Optional[Exception] = None) -> None:
        super().__init__(*args)
        self.cause = cause


class ClientSessionAuthTemporaryCredentialsMetadata(typing.TypedDict):
    access_key: str
    secret_key: str
    token: str
    expiry_time: str


class ClientSessionAuthTemporaryCredentials:
    def __init__(
        self,
        *,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        aws_region: str,
        aws_selling_partner_role: str,
        aws_selling_partner_role_session_name: str,
    ) -> None:
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_region = aws_region
        self.aws_selling_partner_role = aws_selling_partner_role
        self.aws_selling_partner_role_session_name = aws_selling_partner_role_session_name
        self.sts_client = boto3.Session(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.aws_region,
        ).client("sts")

    def _get_refreshable_credentials_metadata(
        self,
    ) -> ClientSessionAuthTemporaryCredentialsMetadata:
        try:
            _result: typing.Dict[str, typing.Dict[str, str]] = self.sts_client.assume_role(
                RoleArn=self.aws_selling_partner_role,
                RoleSessionName=self.aws_selling_partner_role_session_name,
            )
            _data = {
                "access_key": _result["Credentials"]["AccessKeyId"],
                "secret_key": _result["Credentials"]["SecretAccessKey"],
                "token": _result["Credentials"]["SessionToken"],
                "expiry_time": _result["Credentials"]["Expiration"].isoformat(),  # type: ignore
            }
            return _data  # type: ignore
        except Exception as error:
            raise ClientSessionAuthTemporaryCredentialsError(cause=error)

    def get_refreshable_credentials(self) -> botocore.credentials.RefreshableCredentials:
        return botocore.credentials.RefreshableCredentials.create_from_metadata(
            metadata=self._get_refreshable_credentials_metadata(),
            refresh_using=self._get_refreshable_credentials_metadata,
            method="sts-assume-role",
        )


class ClientSessionAuthAccessTokenError(Exception):
    def __init__(self, *args, cause: typing.Optional[Exception] = None) -> None:
        super().__init__(*args)
        self.cause = cause


class ClientSessionAuthAccessTokenData(typing.TypedDict):
    access_token: str
    expires_at: int


class ClientSessionAuthAccessToken:
    def __init__(self, *, client_id: str, client_secret: str, refresh_token: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.data: typing.Optional[ClientSessionAuthAccessTokenData] = None

    def current_time(self):
        return int(datetime.datetime.now().timestamp())

    def _get_payload(self):
        return {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
        }

    def _get_access_token_data(self) -> ClientSessionAuthAccessTokenData:
        try:
            _session = requests.Session()
            _payload = self._get_payload()
            _response = _session.post("https://api.amazon.com/auth/o2/token", data=_payload)
            _response.raise_for_status()
            _result: typing.Dict = _response.json()
            _data = {
                "access_token": _result["access_token"],
                "expires_at": self.current_time() + int(_result["expires_in"]),
            }
            return _data  # type: ignore
        except Exception as error:
            raise ClientSessionAuthAccessTokenError(cause=error)

    def get_access_token(self) -> str:
        if self.data is None or not self.current_time() < self.data.get("expires_at", 0):
            self.data = self._get_access_token_data()

        data = self.data
        if data is None:
            raise RuntimeError("Access token data was not initialized")
        return data["access_token"]


class ClientSessionAuth(requests_aws4auth.AWS4Auth):
    def __init__(
        self,
        *,
        selling_partner_app_client_id: str,
        selling_partner_app_client_secret: str,
        selling_partner_app_refresh_token: str,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        aws_region: str,
        aws_selling_partner_role: str,
        aws_selling_partner_role_session_name: str,
    ):
        self.selling_partner_app_client_id = selling_partner_app_client_id
        self.selling_partner_app_client_secret = selling_partner_app_client_secret
        self.selling_partner_app_refresh_token = selling_partner_app_refresh_token
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_selling_partner_role = aws_selling_partner_role
        self.aws_selling_partner_role_session_name = aws_selling_partner_role_session_name
        self.aws_region = aws_region
        self.aws_service = "execute-api"
        self.access_token = ClientSessionAuthAccessToken(
            client_id=self.selling_partner_app_client_id,
            client_secret=self.selling_partner_app_client_secret,
            refresh_token=self.selling_partner_app_refresh_token,
        )

        super().__init__(
            refreshable_credentials=ClientSessionAuthTemporaryCredentials(
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                aws_region=self.aws_region,
                aws_selling_partner_role=self.aws_selling_partner_role,
                aws_selling_partner_role_session_name=self.aws_selling_partner_role_session_name,
            ).get_refreshable_credentials(),
            region=self.aws_region,
            service=self.aws_service,
        )

    def _get_user_agent(self) -> str:
        language_info = f"Python/{platform.python_version()}"
        platform_info = f"{platform.system()}/{platform.release()}"
        return f"danilo-poc/0.0.1 (Language={language_info}; Platform={platform_info})"

    def _get_access_token(self):
        return self.access_token.get_access_token()

    def __call__(self, req):
        req.headers["User-agent"] = self._get_user_agent()
        req.headers["Content-Type"] = "application/json; charset=utf-8"
        req.headers["Accept"] = "application/json"
        req.headers["x-amz-access-token"] = self._get_access_token()
        return super().__call__(req)
