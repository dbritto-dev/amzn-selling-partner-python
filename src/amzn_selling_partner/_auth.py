import asyncio
import platform
import time
import typing

import boto3
import botocore.auth
import botocore.awsrequest
import botocore.credentials
import httpx2

from . import _exceptions

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"  # noqa # nosec B105


def _user_agent() -> str:
    language_info = f"Python/{platform.python_version()}"
    platform_info = f"{platform.system()}/{platform.release()}"
    return f"danilo-poc/0.0.1 (Language={language_info}; Platform={platform_info})"


class _LWAToken:
    """LWA (Login with Amazon) OAuth access token, cached and refreshed on expiry."""

    def __init__(self, *, client_id: str, client_secret: str, refresh_token: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token: typing.Optional[str] = None
        self._expires_at: float = 0.0

    def needs_refresh(self) -> bool:
        return self._access_token is None or not time.time() < self._expires_at

    def build_refresh_request(self) -> httpx2.Request:
        return httpx2.Request(
            "POST",
            LWA_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
            },
        )

    def consume_refresh_response(self, response: httpx2.Response) -> None:
        if response.is_error:
            raise _exceptions.SPAPIAuthError(
                f"LWA token refresh failed with status {response.status_code}"
            )
        payload = response.json()
        self._access_token = payload["access_token"]
        self._expires_at = time.time() + int(payload["expires_in"])

    @property
    def access_token(self) -> str:
        if self._access_token is None:
            raise RuntimeError("Access token was not initialized")
        return self._access_token


class _STSCredentials:
    """AWS STS-assumed role credentials, auto-refreshed by botocore when near expiry."""

    def __init__(
        self,
        *,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        aws_region: str,
        aws_role_arn: str,
        aws_role_session_name: str,
    ) -> None:
        self.aws_region = aws_region
        self._role_arn = aws_role_arn
        self._role_session_name = aws_role_session_name
        self._sts_client = boto3.Session(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region,
        ).client("sts")
        self._refreshable = botocore.credentials.RefreshableCredentials.create_from_metadata(
            metadata=self._fetch_metadata(),
            refresh_using=self._fetch_metadata,
            method="sts-assume-role",
        )

    def _fetch_metadata(self) -> typing.Dict[str, str]:
        try:
            result = self._sts_client.assume_role(
                RoleArn=self._role_arn,
                RoleSessionName=self._role_session_name,
            )
            credentials = result["Credentials"]
            return {
                "access_key": credentials["AccessKeyId"],
                "secret_key": credentials["SecretAccessKey"],
                "token": credentials["SessionToken"],
                "expiry_time": credentials["Expiration"].isoformat(),
            }
        except Exception as error:
            # boto3/botocore expose no single clean exception base for STS/network/credential
            # failures here, so this is the one sanctioned bare `except Exception` in the SDK.
            raise _exceptions.SPAPIAuthError("STS assume_role failed", cause=error) from error

    def get_frozen_credentials(self) -> botocore.credentials.ReadOnlyCredentials:
        return self._refreshable.get_frozen_credentials()


class SPAPIAuth(httpx2.Auth):
    """Signs SP-API requests with AWS SigV4 and an LWA bearer token.

    Overrides `sync_auth_flow`/`async_auth_flow` directly (rather than the shared
    `auth_flow` generator) because AWS STS credential refresh is a blocking boto3 call that
    must be offloaded to a thread on the async path but not on the sync path.
    """

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
    ) -> None:
        self._lwa = _LWAToken(
            client_id=selling_partner_app_client_id,
            client_secret=selling_partner_app_client_secret,
            refresh_token=selling_partner_app_refresh_token,
        )
        self._sts = _STSCredentials(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_region=aws_region,
            aws_role_arn=aws_selling_partner_role,
            aws_role_session_name=aws_selling_partner_role_session_name,
        )
        # Computed once here, not per request.
        self._default_headers = {
            "User-Agent": _user_agent(),
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }

    def _apply_default_headers(self, request: httpx2.Request) -> None:
        request.headers.update(self._default_headers)

    def _sign(
        self, request: httpx2.Request, credentials: botocore.credentials.ReadOnlyCredentials
    ) -> None:
        aws_request = botocore.awsrequest.AWSRequest(
            method=request.method,
            url=str(request.url),
            data=request.content,
            headers=dict(request.headers),
        )
        botocore.auth.SigV4Auth(credentials, "execute-api", self._sts.aws_region).add_auth(
            aws_request
        )
        request.headers.update(dict(aws_request.headers))

    def sync_auth_flow(
        self, request: httpx2.Request
    ) -> typing.Generator[httpx2.Request, httpx2.Response, None]:
        request.read()
        self._apply_default_headers(request)
        if self._lwa.needs_refresh():
            token_response = yield self._lwa.build_refresh_request()
            token_response.read()
            self._lwa.consume_refresh_response(token_response)
        request.headers["x-amz-access-token"] = self._lwa.access_token
        credentials = self._sts.get_frozen_credentials()
        self._sign(request, credentials)
        yield request

    async def async_auth_flow(
        self, request: httpx2.Request
    ) -> typing.AsyncGenerator[httpx2.Request, httpx2.Response]:
        await request.aread()
        self._apply_default_headers(request)
        if self._lwa.needs_refresh():
            token_response = yield self._lwa.build_refresh_request()
            await token_response.aread()
            self._lwa.consume_refresh_response(token_response)
        request.headers["x-amz-access-token"] = self._lwa.access_token
        credentials = await asyncio.to_thread(self._sts.get_frozen_credentials)
        await asyncio.to_thread(self._sign, request, credentials)
        yield request
