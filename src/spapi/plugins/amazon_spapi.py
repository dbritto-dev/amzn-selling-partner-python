"""Amazon Selling Partner API plugin and the preconfigured clients.

Everything Amazon-specific lives here (and in ``spapi.plugins._amazon``):
regional servers, rate-limit tables, pagination overrides, Restricted Data
Token requirements, grantless scopes, LWA auth, document helpers, sandbox
examples and notification models. The core never imports this module.
"""

from __future__ import annotations

import logging
import os
import pathlib
from collections.abc import Iterable, Mapping
from typing import Any

from ..client import AsyncClient, Client
from ..compile.operations import detect_pagination
from ..runtime._pagination import Pagination
from ..runtime._types import RequestOptions
from ..spec.ir import Document, Operation, Server
from ._amazon.auth import ACCESS_TOKEN_HEADER, AsyncLWAAuth, LWAAuth, LWACredentials, MemoryTokenStore, Token, TokenStore
from ._amazon.documents import AsyncDocuments, Documents
from ._amazon.naming import ALIASES, api_naming, spec_files
from ._amazon.notifications import Notifications
from ._amazon.pagination import DROP_PARAMS_ON_NEXT, override_for
from ._amazon.rate_limits import annotate_rate_limits, parse_rate_limit
from ._amazon.rdt import GRANTLESS, RESTRICTED_REPORT_TYPES, RestrictedOperation, restricted_for
from ._amazon.regions import LWA_TOKEN_URL, Marketplace, Region
from ._amazon.sandbox import SandboxExample, is_dynamic_sandbox, sandbox_examples

log = logging.getLogger("spapi.plugins.amazon")

_HERE = pathlib.Path(__file__).resolve().parent


def default_spec_dir() -> pathlib.Path:
    """The vendored ``models`` directory (packaged symlink, or the submodule)."""
    env = os.environ.get("SPAPI_AMAZON_MODELS")
    candidates = [pathlib.Path(env)] if env else []
    candidates += [
        _HERE / "_amazon" / "models",
        _HERE.parents[2] / "spec" / "selling-partner-api-models" / "models",
    ]
    for c in candidates:
        if c.is_dir() and any(c.glob("*/*.json")):
            return c
    raise FileNotFoundError(
        "Amazon SP-API models not found. Check out the git submodule "
        "(git submodule update --init) or set SPAPI_AMAZON_MODELS to the models directory."
    )


def default_schema_dir() -> pathlib.Path:
    env = os.environ.get("SPAPI_AMAZON_SCHEMAS")
    candidates = [pathlib.Path(env)] if env else []
    candidates += [
        _HERE / "_amazon" / "schemas",
        _HERE.parents[2] / "spec" / "selling-partner-api-models" / "schemas",
    ]
    for c in candidates:
        if (c / "notifications").is_dir():
            return c
    raise FileNotFoundError("Amazon SP-API schemas not found (git submodule update --init, or set SPAPI_AMAZON_SCHEMAS).")


class AmazonPlugin:
    """``annotate`` hook plus discovery/naming hooks for the Amazon models."""

    def __init__(self, *, region: Region = Region.NA, sandbox: bool = False) -> None:
        self.region = region
        self.sandbox = sandbox
        self.unparsed_rate_limits: dict[str, list[str]] = {}

    # -- discovery hooks -------------------------------------------------------------

    def spec_files(self, root: pathlib.Path) -> list[pathlib.Path]:
        return spec_files(root)

    def api_naming(self, path: pathlib.Path) -> tuple[str, str] | None:
        return api_naming(path)

    def aliases(self) -> Mapping[str, str]:
        return ALIASES

    def client_defaults(self) -> Mapping[str, Any]:
        return {"request_id_header": "x-amzn-RequestId", "rate_hint_header": "x-amzn-RateLimit-Limit"}

    # -- annotate --------------------------------------------------------------------

    def annotate(self, document: Document) -> Document:
        named = api_naming(pathlib.Path(document.source))
        api, version = named if named is not None else (pathlib.Path(document.source).stem, "v" + document.version.replace("-", "_"))
        key = f"{api}.{version}"
        document = document.with_operations(tuple(document.operations)).annotated(api=api, version=version)
        document, unparsed = annotate_rate_limits(document, key)
        self.unparsed_rate_limits[key] = unparsed
        ops = tuple(self._annotate_operation(op, document, api, version, key) for op in document.operations)
        servers = (Server(url=self.region.base_url(sandbox=self.sandbox), description=f"{self.region.name}{' sandbox' if self.sandbox else ''}"),)
        return Document(
            title=document.title,
            version=document.version,
            format=document.format,
            source=document.source,
            hash=document.hash,
            description=document.description,
            servers=servers,
            operations=ops,
            schemas=document.schemas,
            extensions=document.extensions,
            annotations=document.annotations,
        )

    def _annotate_operation(self, op: Operation, document: Document, api: str, version: str, key: str) -> Operation:
        ann: dict[str, Any] = {}
        override = override_for(api, version, op.operation_id)
        if override is not None:
            ann["pagination"] = override
        elif (api, op.operation_id) in DROP_PARAMS_ON_NEXT:
            detected = detect_pagination(op, document, key=f"{key}.{op.operation_id}")
            if detected is not None:
                ann["pagination"] = Pagination(
                    items_path=detected.items_path,
                    next_token_path=detected.next_token_path,
                    next_token_param=detected.next_token_param,
                    prev_token_path=detected.prev_token_path,
                    drop_params_on_next=True,
                    source="plugin",
                )
        restricted = restricted_for(api, version, op.operation_id)
        if restricted is not None:
            ann["rdt"] = restricted
        scopes = GRANTLESS.get((api, op.operation_id))
        if scopes:
            ann["grantless_scopes"] = scopes
        examples = sandbox_examples(op)
        if examples:
            ann["sandbox_examples"] = tuple(examples)
        if is_dynamic_sandbox(op):
            ann["sandbox_dynamic"] = True
        return op.annotated(**ann) if ann else op


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


class _SellingPartnerMixin:
    plugin: AmazonPlugin
    region: Region
    sandbox: bool

    @property
    def unparsed_rate_limits(self) -> dict[str, list[str]]:
        """Operations (per loaded API) whose rate-limit table could not be parsed."""
        return dict(self.plugin.unparsed_rate_limits)

    @staticmethod
    def sandbox_examples(op: Any) -> tuple[SandboxExample, ...]:
        compiled = getattr(op, "__spapi_op__", op)
        return tuple(compiled.annotations.get("sandbox_examples", ()))


class SellingPartner(Client, _SellingPartnerMixin):
    """Synchronous Amazon SP-API client.

    Parameters
    ----------
    region, sandbox, marketplace:
        Select the endpoint; ``marketplace`` implies its region.
    client_id, client_secret, refresh_token / credentials:
        LWA credentials (fall back to ``SPAPI_*`` / ``SELLING_PARTNER_APP_*``
        environment variables). Without credentials no auth header is sent.
    token_store:
        Pluggable token cache (default in-memory).
    specs:
        Override the vendored models directory.
    Other keyword arguments go to the runtime client (``http_client=``,
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
        specs: str | os.PathLike[str] | None = None,
        plugins: Iterable[Any] = (),
        auth: Any = None,
        **kwargs: Any,
    ) -> None:
        if marketplace is not None:
            region = marketplace.region
        self.region = region
        self.sandbox = sandbox
        self.marketplace = marketplace
        self.plugin = AmazonPlugin(region=region, sandbox=sandbox)
        creds = _resolve_credentials(credentials, client_id, client_secret, refresh_token)
        base_url = region.base_url(sandbox=sandbox)
        if auth is None and creds is not None:
            auth = LWAAuth(creds, store=token_store, token_url=token_url, base_url=base_url, transport=kwargs.get("transport"))
        super().__init__(specs or default_spec_dir(), base_url=base_url, plugins=[self.plugin, *plugins], auth=auth, **kwargs)
        self.documents = Documents(self)
        self._notifications: Notifications | None = None

    @property
    def notifications_models(self) -> Notifications:
        if self._notifications is None:
            self._notifications = Notifications(default_schema_dir() / "notifications", use_cache=self._core.use_cache)
        return self._notifications

    def close(self) -> None:
        super().close()
        if isinstance(self._auth, LWAAuth):
            self._auth.close()


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
        specs: str | os.PathLike[str] | None = None,
        plugins: Iterable[Any] = (),
        auth: Any = None,
        **kwargs: Any,
    ) -> None:
        if marketplace is not None:
            region = marketplace.region
        self.region = region
        self.sandbox = sandbox
        self.marketplace = marketplace
        self.plugin = AmazonPlugin(region=region, sandbox=sandbox)
        creds = _resolve_credentials(credentials, client_id, client_secret, refresh_token)
        base_url = region.base_url(sandbox=sandbox)
        if auth is None and creds is not None:
            auth = AsyncLWAAuth(creds, store=token_store, token_url=token_url, base_url=base_url, transport=kwargs.get("transport"))
        super().__init__(specs or default_spec_dir(), base_url=base_url, plugins=[self.plugin, *plugins], auth=auth, **kwargs)
        self.documents = AsyncDocuments(self)
        self._notifications: Notifications | None = None

    @property
    def notifications_models(self) -> Notifications:
        if self._notifications is None:
            self._notifications = Notifications(default_schema_dir() / "notifications", use_cache=self._core.use_cache)
        return self._notifications

    async def aclose(self) -> None:
        await super().aclose()
        if isinstance(self._auth, AsyncLWAAuth):
            await self._auth.aclose()


__all__ = [
    "ACCESS_TOKEN_HEADER",
    "LWA_TOKEN_URL",
    "RESTRICTED_REPORT_TYPES",
    "AmazonPlugin",
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
    "SandboxExample",
    "SellingPartner",
    "Token",
    "TokenStore",
    "default_schema_dir",
    "default_spec_dir",
    "parse_rate_limit",
    "sandbox_examples",
    "with_rdt",
]
