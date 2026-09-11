"""Compatibility shims for the old auth classes.

Only the LWA access-token part survives; it delegates to
:class:`spapi.plugins.amazon_spapi.LWAAuth`. The AWS SigV4 classes are gone
(see ``MIGRATION.md``) and raise on use.
"""

from __future__ import annotations

from typing import Any, TypedDict

from spapi.plugins.amazon_spapi import LWAAuth, LWACredentials


class ClientSessionAuthAccessTokenError(Exception):
    def __init__(self, *args: Any, cause: Exception | None = None) -> None:
        super().__init__(*args)
        self.cause = cause


class ClientSessionAuthAccessTokenData(TypedDict):
    access_token: str
    expires_at: int


class ClientSessionAuthAccessToken:
    """Refresh-token grant with caching (single instance per client)."""

    def __init__(self, *, client_id: str, client_secret: str, refresh_token: str, **options: Any) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._auth = LWAAuth(LWACredentials(client_id=client_id, client_secret=client_secret, refresh_token=refresh_token), **options)

    def get_access_token(self) -> str:
        try:
            return self._auth.access_token()
        except Exception as error:  # noqa: BLE001 - old API contract wraps every failure
            raise ClientSessionAuthAccessTokenError(cause=error) from error


class ClientSessionAuthTemporaryCredentialsError(Exception):
    def __init__(self, *args: Any, cause: Exception | None = None) -> None:
        super().__init__(*args)
        self.cause = cause


def _removed(*_args: Any, **_kwargs: Any) -> Any:
    raise NotImplementedError(
        "AWS Signature V4 authentication was removed: the Selling Partner API only needs the LWA access token. See MIGRATION.md."
    )


ClientSessionAuthTemporaryCredentials = _removed
ClientSessionAuth = _removed

__all__ = [
    "ClientSessionAuth",
    "ClientSessionAuthAccessToken",
    "ClientSessionAuthAccessTokenData",
    "ClientSessionAuthAccessTokenError",
    "ClientSessionAuthTemporaryCredentials",
    "ClientSessionAuthTemporaryCredentialsError",
]
