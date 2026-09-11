"""Login with Amazon (LWA) authentication.

* refresh-token grant per seller, ``client_credentials`` + scopes for
  grantless operations,
* in-memory token cache with expiry and single-flight refresh
  (``threading.Lock`` / ``asyncio.Lock`` per cache key), pluggable store,
* Restricted Data Tokens obtained through the Tokens API for operations marked
  by the plugin (``annotations["rdt"]``).

An explicit ``x-amz-access-token`` header on a request (e.g. an RDT obtained
by the caller) is left untouched.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlencode

import httpx2
from pydantic_core import from_json, to_json

from ...runtime._errors import APIConnectionError, AuthenticationError
from ...spec._jsonutil import as_object
from .rdt import RestrictedOperation
from .regions import LWA_TOKEN_URL

if TYPE_CHECKING:
    from ...compile.operations import CompiledOp

log = logging.getLogger("amzn_selling_partner.plugins.amazon.auth")

ACCESS_TOKEN_HEADER = "x-amz-access-token"
RDT_PATH = "/tokens/2021-03-01/restrictedDataToken"


@dataclass(slots=True, frozen=True)
class Token:
    access_token: str
    expires_at: float  # unix time

    def is_valid(self, *, leeway: float = 60.0) -> bool:
        return time.time() + leeway < self.expires_at


class TokenStore(Protocol):
    def get(self, key: str) -> Token | None: ...

    def set(self, key: str, token: Token) -> None: ...


class MemoryTokenStore:
    __slots__ = ("_lock", "_tokens")

    def __init__(self) -> None:
        self._tokens: dict[str, Token] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Token | None:
        with self._lock:
            return self._tokens.get(key)

    def set(self, key: str, token: Token) -> None:
        with self._lock:
            self._tokens[key] = token

    def clear(self) -> None:
        with self._lock:
            self._tokens.clear()


@dataclass(slots=True, frozen=True, kw_only=True)
class LWACredentials:
    client_id: str
    client_secret: str
    refresh_token: str | None = None

    @classmethod
    def from_env(cls) -> LWACredentials | None:
        env = os.environ
        client_id = env.get("AMZN_SELLING_PARTNER_CLIENT_ID") or env.get("SELLING_PARTNER_APP_CLIENT_ID")
        client_secret = env.get("AMZN_SELLING_PARTNER_CLIENT_SECRET") or env.get("SELLING_PARTNER_APP_CLIENT_SECRET")
        refresh_token = env.get("AMZN_SELLING_PARTNER_REFRESH_TOKEN") or env.get("SELLING_PARTNER_APP_REFRESH_TOKEN")
        if not client_id or not client_secret:
            return None
        return cls(client_id=client_id, client_secret=client_secret, refresh_token=refresh_token or None)

    def fingerprint(self) -> str:
        h = hashlib.sha256(f"{self.client_id}:{self.refresh_token or ''}".encode()).hexdigest()
        return h[:16]


class _LWABase:
    def __init__(
        self,
        credentials: LWACredentials,
        *,
        store: TokenStore | None = None,
        token_url: str = LWA_TOKEN_URL,
        base_url: str | None = None,
        transport: Any = None,
        leeway: float = 60.0,
    ) -> None:
        self.credentials = credentials
        self.store: TokenStore = store or MemoryTokenStore()
        self.token_url = token_url
        self.base_url = base_url  # for the Tokens API (RDT); set by the client
        self._transport = transport
        self._leeway = leeway
        self._fp = credentials.fingerprint()

    # -- keys ------------------------------------------------------------------------

    def _refresh_key(self) -> str:
        return f"lwa:refresh:{self._fp}"

    def _grantless_key(self, scopes: tuple[str, ...]) -> str:
        return f"lwa:cc:{self._fp}:{' '.join(scopes)}"

    @staticmethod
    def _rdt_key(method: str, path: str, elements: tuple[str, ...]) -> str:
        return f"rdt:{method}:{path}:{','.join(elements)}"

    # -- classification --------------------------------------------------------------

    @staticmethod
    def classify(op: CompiledOp, request: httpx2.Request) -> tuple[str, tuple[str, ...]]:
        """Return ``("rdt", data_elements)``, ``("grantless", scopes)`` or ``("lwa", ())``.

        Operations marked as always-restricted get an RDT unconditionally.
        Operations that return PII only on request (``data_elements`` set)
        get one when the call opted in through ``RequestOptions(auth={"rdt":
        True | [elements]})`` (see ``with_rdt``).
        """
        scopes = op.annotations.get("grantless_scopes")
        if scopes:
            return "grantless", tuple(scopes)
        rdt = op.annotations.get("rdt")
        hints = as_object(request.extensions.get("auth_hints")) or {}
        wanted: Any = hints.get("rdt")
        if isinstance(rdt, RestrictedOperation):
            if rdt.data_elements is None:
                return "rdt", ()
            if wanted:
                elements = tuple(rdt.data_elements) if wanted is True else tuple(str(v) for v in wanted)
                return "rdt", elements
        elif wanted:
            # caller insists on an RDT for an operation the table does not list
            return "rdt", () if wanted is True else tuple(str(v) for v in wanted)
        return "lwa", ()

    # -- wire ------------------------------------------------------------------------

    def _grant_form(self, kind: str, scopes: tuple[str, ...]) -> bytes:
        c = self.credentials
        if kind == "grantless":
            form = {
                "grant_type": "client_credentials",
                "scope": " ".join(scopes),
                "client_id": c.client_id,
                "client_secret": c.client_secret,
            }
        else:
            if not c.refresh_token:
                raise ValueError("a refresh token is required for non-grantless operations")
            form = {
                "grant_type": "refresh_token",
                "refresh_token": c.refresh_token,
                "client_id": c.client_id,
                "client_secret": c.client_secret,
            }
        return urlencode(form).encode()

    def _token_request(self, kind: str, scopes: tuple[str, ...]) -> httpx2.Request:
        return httpx2.Request(
            "POST",
            self.token_url,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8", "Accept": "application/json"},
            content=self._grant_form(kind, scopes),
        )

    def _rdt_request(self, access_token: str, method: str, path: str, elements: tuple[str, ...]) -> httpx2.Request:
        if not self.base_url:
            raise ValueError("LWA auth needs base_url to request Restricted Data Tokens")
        resource: dict[str, Any] = {"method": method, "path": path}
        if elements:
            resource["dataElements"] = list(elements)
        return httpx2.Request(
            "POST",
            self.base_url.rstrip("/") + RDT_PATH,
            headers={"Content-Type": "application/json", "Accept": "application/json", ACCESS_TOKEN_HEADER: access_token},
            content=to_json({"restrictedResources": [resource]}),
        )

    @staticmethod
    def _parse(response: httpx2.Response, *, what: str) -> Token:
        data: Any
        try:
            data = from_json(response.content) if response.content else {}
        except ValueError:
            data = response.text
        payload = as_object(data)
        if response.status_code >= 400 or payload is None:
            raise AuthenticationError(f"{what} request failed with HTTP {response.status_code}", response=response, body=data)
        token: Any = payload.get("access_token") or payload.get("restrictedDataToken")
        if not isinstance(token, str):
            raise AuthenticationError(f"{what} response has no token", response=response, body=data)
        expires_in: Any = payload.get("expires_in", 3600)
        try:
            ttl = float(expires_in)
        except (TypeError, ValueError):
            ttl = 3600.0
        return Token(access_token=token, expires_at=time.time() + ttl)


class LWAAuth(_LWABase):
    """Synchronous LWA hook."""

    def __init__(self, credentials: LWACredentials, *, http_client: httpx2.Client | None = None, **kwargs: Any) -> None:
        super().__init__(credentials, **kwargs)
        self._http = http_client
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _client(self) -> httpx2.Client:
        if self._http is None:
            self._http = httpx2.Client(transport=self._transport, timeout=httpx2.Timeout(30.0, connect=10.0))
        return self._http

    def _lock(self, key: str) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = self._locks[key] = threading.Lock()
            return lock

    def _send(self, request: httpx2.Request, what: str) -> Token:
        try:
            response = self._client().send(request)
        except httpx2.TransportError as exc:
            raise APIConnectionError(f"{what} request failed: {exc}", request=request, cause=exc) from exc
        return self._parse(response, what=what)

    def access_token(self, *, scopes: tuple[str, ...] = ()) -> str:
        """LWA access token (refresh-token grant, or client_credentials when scopes are given)."""
        kind = "grantless" if scopes else "lwa"
        key = self._grantless_key(scopes) if scopes else self._refresh_key()
        token = self.store.get(key)
        if token is not None and token.is_valid(leeway=self._leeway):
            return token.access_token
        with self._lock(key):  # single flight
            token = self.store.get(key)
            if token is not None and token.is_valid(leeway=self._leeway):
                return token.access_token
            log.debug("refreshing LWA token (%s)", kind)
            token = self._send(self._token_request(kind, scopes), "LWA token")
            self.store.set(key, token)
            return token.access_token

    def restricted_data_token(self, method: str, path: str, data_elements: tuple[str, ...] = ()) -> str:
        key = self._rdt_key(method, path, data_elements)
        token = self.store.get(key)
        if token is not None and token.is_valid(leeway=self._leeway):
            return token.access_token
        with self._lock(key):
            token = self.store.get(key)
            if token is not None and token.is_valid(leeway=self._leeway):
                return token.access_token
            log.debug("requesting RDT for %s %s %s", method, path, data_elements)
            token = self._send(self._rdt_request(self.access_token(), method, path, data_elements), "RDT")
            self.store.set(key, token)
            return token.access_token

    def before_request(self, op: CompiledOp, request: httpx2.Request) -> Mapping[str, str] | None:
        if ACCESS_TOKEN_HEADER in request.headers:
            return None
        kind, extra = self.classify(op, request)
        if kind == "rdt":
            token = self.restricted_data_token(request.method, request.url.path, extra)
        elif kind == "grantless":
            token = self.access_token(scopes=extra)
        else:
            token = self.access_token()
        return {ACCESS_TOKEN_HEADER: token}

    def close(self) -> None:
        if self._http is not None:
            self._http.close()


class AsyncLWAAuth(_LWABase):
    """Asynchronous LWA hook (single event loop)."""

    def __init__(self, credentials: LWACredentials, *, http_client: httpx2.AsyncClient | None = None, **kwargs: Any) -> None:
        super().__init__(credentials, **kwargs)
        self._http = http_client
        self._locks: dict[str, asyncio.Lock] = {}

    def _client(self) -> httpx2.AsyncClient:
        if self._http is None:
            self._http = httpx2.AsyncClient(transport=self._transport, timeout=httpx2.Timeout(30.0, connect=10.0))
        return self._http

    def _lock(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = self._locks[key] = asyncio.Lock()
        return lock

    async def _send(self, request: httpx2.Request, what: str) -> Token:
        try:
            response = await self._client().send(request)
        except httpx2.TransportError as exc:
            raise APIConnectionError(f"{what} request failed: {exc}", request=request, cause=exc) from exc
        return self._parse(response, what=what)

    async def access_token(self, *, scopes: tuple[str, ...] = ()) -> str:
        kind = "grantless" if scopes else "lwa"
        key = self._grantless_key(scopes) if scopes else self._refresh_key()
        token = self.store.get(key)
        if token is not None and token.is_valid(leeway=self._leeway):
            return token.access_token
        async with self._lock(key):
            token = self.store.get(key)
            if token is not None and token.is_valid(leeway=self._leeway):
                return token.access_token
            log.debug("refreshing LWA token (%s)", kind)
            token = await self._send(self._token_request(kind, scopes), "LWA token")
            self.store.set(key, token)
            return token.access_token

    async def restricted_data_token(self, method: str, path: str, data_elements: tuple[str, ...] = ()) -> str:
        key = self._rdt_key(method, path, data_elements)
        token = self.store.get(key)
        if token is not None and token.is_valid(leeway=self._leeway):
            return token.access_token
        async with self._lock(key):
            token = self.store.get(key)
            if token is not None and token.is_valid(leeway=self._leeway):
                return token.access_token
            log.debug("requesting RDT for %s %s %s", method, path, data_elements)
            token = await self._send(self._rdt_request(await self.access_token(), method, path, data_elements), "RDT")
            self.store.set(key, token)
            return token.access_token

    async def before_request(self, op: CompiledOp, request: httpx2.Request) -> Mapping[str, str] | None:
        if ACCESS_TOKEN_HEADER in request.headers:
            return None
        kind, extra = self.classify(op, request)
        if kind == "rdt":
            token = await self.restricted_data_token(request.method, request.url.path, extra)
        elif kind == "grantless":
            token = await self.access_token(scopes=extra)
        else:
            token = await self.access_token()
        return {ACCESS_TOKEN_HEADER: token}

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()


__all__ = ["ACCESS_TOKEN_HEADER", "AsyncLWAAuth", "LWAAuth", "LWACredentials", "MemoryTokenStore", "Token", "TokenStore"]
