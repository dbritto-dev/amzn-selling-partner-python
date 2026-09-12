"""Amazon Selling Partner API preconfigured clients.

Everything Amazon-specific lives here and in ``amzn_selling_partner.plugins._amazon``:
regional servers, LWA auth with Restricted Data Tokens and grantless scopes,
document helpers and notification models. Rate limits and
pagination helpers are generated into the resource modules by ``codegen/``.
"""

from __future__ import annotations

import logging
from typing import Any

from ..sdk._http import RequestOptions
from ..sdk.client import AsyncClient, Client
from ..sdk.resources import OPERATIONS
from ._amazon.auth import ACCESS_TOKEN_HEADER, AsyncLWAAuth, LWAAuth, LWACredentials, MemoryTokenStore, Token, TokenStore
from ._amazon.documents import AsyncDocuments, Documents
from ._amazon.notifications import Notifications
from ._amazon.rdt import GRANTLESS, RESTRICTED, RESTRICTED_REPORT_TYPES, RestrictedOperation, restricted_for
from ._amazon.regions import LWA_TOKEN_URL, Marketplace, Region

log = logging.getLogger("amzn_selling_partner.plugins.amazon")


def with_rdt(*data_elements: str, **options: Any) -> RequestOptions:
    """Per-call options asking for a Restricted Data Token.

    ``with_rdt("buyerInfo", "shippingAddress")`` requests those data elements;
    ``with_rdt()`` requests the operation's default (all elements in the table,
    or a plain RDT for report documents). Extra keyword arguments are passed to
    ``RequestOptions``.
    """
    return RequestOptions(auth={"rdt": list(data_elements) or True}, **options)


def _resolve_credentials(
    credentials: LWACredentials | None,
    client_id: str | None,
    client_secret: str | None,
    refresh_token: str | None,
) -> LWACredentials | None:
    if credentials is not None:
        return credentials
    if client_id and client_secret:
        return LWACredentials(client_id=client_id, client_secret=client_secret, refresh_token=refresh_token)
    env = LWACredentials.from_env()
    if env is not None and refresh_token:
        return LWACredentials(client_id=env.client_id, client_secret=env.client_secret, refresh_token=refresh_token)
    return env


def unparsed_rate_limits() -> dict[str, list[str]]:
    """Operations (per resource module) whose description carried no parseable
    rate-limit table when the code was generated (they run unthrottled unless
    ``default_rate_limit`` is set)."""
    out: dict[str, list[str]] = {}
    for key, (_method, _http, _path, _paginated, has_limit) in OPERATIONS.items():
        if has_limit:
            continue
        module, _, operation_id = key.partition(".")
        out.setdefault(module, []).append(operation_id.split(":")[0])
    return out


class _SellingPartnerMixin:
    region: Region
    sandbox: bool
    marketplace: Marketplace | None

    @property
    def notifications_models(self) -> Notifications:
        return Notifications()

    @staticmethod
    def unparsed_rate_limits() -> dict[str, list[str]]:
        return unparsed_rate_limits()


class SellingPartner(Client, _SellingPartnerMixin):
    """Synchronous Amazon SP-API client.

    Parameters
    ----------
    region, sandbox, marketplace:
        Select the endpoint; ``marketplace`` implies its region.
    client_id, client_secret, refresh_token / credentials:
        LWA credentials (fall back to ``AMZN_SELLING_PARTNER_*`` /
        ``SELLING_PARTNER_APP_*`` environment variables). Without credentials
        no auth header is sent.
    token_store:
        Pluggable token cache (default in-memory).
    Other keyword arguments go to the generated client (``http_client=``,
    ``transport=``, ``timeout=``, ``max_retries=``, ``throttle=``, ...).
    """

    def __init__(
        self,
        *,
        region: Region = Region.NA,
        sandbox: bool = False,
        marketplace: Marketplace | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        credentials: LWACredentials | None = None,
        token_store: TokenStore | None = None,
        token_url: str = LWA_TOKEN_URL,
        auth: Any = None,
        **kwargs: Any,
    ) -> None:
        if marketplace is not None:
            region = marketplace.region
        self.region = region
        self.sandbox = sandbox
        self.marketplace = marketplace
        creds = _resolve_credentials(credentials, client_id, client_secret, refresh_token)
        base_url = region.base_url(sandbox=sandbox)
        if auth is None and creds is not None:
            auth = LWAAuth(creds, store=token_store, token_url=token_url, base_url=base_url, transport=kwargs.get("transport"))
        super().__init__(base_url=base_url, auth=auth, **kwargs)
        self.documents = Documents(self)

    def close(self) -> None:
        super().close()
        if isinstance(self.http.auth, LWAAuth):
            self.http.auth.close()


class AsyncSellingPartner(AsyncClient, _SellingPartnerMixin):
    """Asynchronous Amazon SP-API client; see ``SellingPartner``."""

    def __init__(
        self,
        *,
        region: Region = Region.NA,
        sandbox: bool = False,
        marketplace: Marketplace | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        refresh_token: str | None = None,
        credentials: LWACredentials | None = None,
        token_store: TokenStore | None = None,
        token_url: str = LWA_TOKEN_URL,
        auth: Any = None,
        **kwargs: Any,
    ) -> None:
        if marketplace is not None:
            region = marketplace.region
        self.region = region
        self.sandbox = sandbox
        self.marketplace = marketplace
        creds = _resolve_credentials(credentials, client_id, client_secret, refresh_token)
        base_url = region.base_url(sandbox=sandbox)
        if auth is None and creds is not None:
            auth = AsyncLWAAuth(creds, store=token_store, token_url=token_url, base_url=base_url, transport=kwargs.get("transport"))
        super().__init__(base_url=base_url, auth=auth, **kwargs)
        self.documents = AsyncDocuments(self)

    async def aclose(self) -> None:
        await super().aclose()
        if isinstance(self.http.auth, AsyncLWAAuth):
            await self.http.auth.aclose()


__all__ = [
    "ACCESS_TOKEN_HEADER",
    "GRANTLESS",
    "LWA_TOKEN_URL",
    "RESTRICTED",
    "RESTRICTED_REPORT_TYPES",
    "AsyncDocuments",
    "AsyncLWAAuth",
    "AsyncSellingPartner",
    "Documents",
    "LWAAuth",
    "LWACredentials",
    "Marketplace",
    "MemoryTokenStore",
    "Notifications",
    "Region",
    "RestrictedOperation",
    "SellingPartner",
    "Token",
    "TokenStore",
    "restricted_for",
    "unparsed_rate_limits",
    "with_rdt",
]
