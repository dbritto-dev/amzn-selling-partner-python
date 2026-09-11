"""Generic ``Client`` / ``AsyncClient`` over a directory of specs, and the
Amazon-preconfigured ``SellingPartner`` / ``AsyncSellingPartner``.

``client.<api>`` loads and compiles that API's spec(s) on first access;
``client.<api>.<version>`` is a resource with one method per operation and
``client.<api>.latest`` an alias for the highest version. ``preload()`` builds
everything.
"""

from __future__ import annotations

import logging
import os
import pathlib
import re
import threading
import time
from collections.abc import Iterable, Mapping
from typing import Any

from .compile.models import ModelNamespace, build_models
from .compile.naming import identifier, snake_case
from .compile.operations import CompiledOp, compile_operations
from .compile.resources import AsyncResource, GroupBy, SyncResource, build_resources
from .plugins import default_spec_files, run_plugins
from .runtime._base_client import AsyncAPIClient, SyncAPIClient
from .spec.ir import Document
from .spec.loader import load_document

log = logging.getLogger("spapi.client")

_VERSION_SUFFIX = re.compile(r"(?:[_-]|(?<=[a-z])V)(?P<v>\d{4}-\d{2}-\d{2}|\d+)$")


def default_api_naming(path: pathlib.Path) -> tuple[str, str | None]:
    """``orders_2021-08-01.json`` -> ``("orders", "v2021_08_01")``; a stem
    without a version suffix returns ``None`` for the version (resolved from
    ``info.version`` once the document is loaded)."""
    stem = path.stem
    m = _VERSION_SUFFIX.search(stem)
    if m:
        return identifier(snake_case(stem[: m.start()])), "v" + m.group("v").replace("-", "_")
    return identifier(snake_case(stem)), None


def version_key(v: str) -> tuple[int, str]:
    body = v[1:] if v.startswith("v") else v
    return (1, body) if "_" in body else (0, body.zfill(6))


def normalize_version(raw: str) -> str:
    v = re.sub(r"[^0-9a-zA-Z_]+", "_", raw.strip().lstrip("vV")).strip("_")
    return "v" + (v or "0")


class APIVersion:
    """One spec file: loaded, annotated, compiled once; cached afterwards."""

    def __init__(self, owner: _ClientCore, api: str, version: str, path: pathlib.Path) -> None:
        self.owner = owner
        self.api = api
        self.version = version
        self.path = path
        self.key = f"{api}.{version}"
        self._document: Document | None = None
        self._models: ModelNamespace | None = None
        self._ops: list[CompiledOp] | None = None
        self._resources: dict[str, Any] | None = None
        self._lock = threading.RLock()
        self.build_ms: float | None = None

    @property
    def document(self) -> Document:
        doc = self._document
        if doc is None:
            with self._lock:
                doc = self._document
                if doc is None:
                    doc = run_plugins(load_document(self.path, use_cache=self.owner.use_cache), self.owner.plugins)
                    self._document = doc
        return doc

    @property
    def models(self) -> ModelNamespace:
        ns = self._models
        if ns is None:
            ns = build_models(self.document, key=self.key, enum_mode=self.owner.enum_mode)
            self._models = ns
        return ns

    @property
    def operations(self) -> list[CompiledOp]:
        ops = self._ops
        if ops is None:
            with self._lock:
                ops = self._ops
                if ops is None:
                    started = time.perf_counter()
                    ops = compile_operations(self.document, self.models, key_prefix=self.key)
                    self._ops = ops
                    self.build_ms = (time.perf_counter() - started) * 1000
                    log.debug("compiled %s: %d operations in %.1f ms", self.key, len(ops), self.build_ms)
        return ops

    def resources(self) -> dict[str, Any]:
        res = self._resources
        if res is None:
            pairs = build_resources(self.operations, name=self.api, group_by=self.owner.group_by)
            res = {}
            for name, pair in pairs.items():
                cls = pair.async_cls if self.owner.is_async else pair.sync_cls
                res[name] = cls(self.owner.runtime, self.models)
            self._resources = res
        return res


class APIVersions:
    """``client.orders`` -> versions container (``.v0``, ``.v2026_01_01``, ``.latest``)."""

    def __init__(self, owner: _ClientCore, api: str, versions: dict[str, pathlib.Path]) -> None:
        self._owner = owner
        self._api = api
        self._versions = {v: APIVersion(owner, api, v, p) for v, p in versions.items()}
        self._latest = max(self._versions, key=version_key)

    @property
    def api(self) -> str:
        return self._api

    @property
    def versions(self) -> list[str]:
        return sorted(self._versions, key=version_key)

    @property
    def latest(self) -> Any:
        return self.__getattr__(self._latest)

    def version(self, name: str) -> APIVersion:
        return self._versions[name]

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        av = self._versions.get(name)
        if av is None:
            raise AttributeError(f"API {self._api!r} has no version {name!r}; available: {', '.join(self.versions)}")
        resources = av.resources()
        if self._owner.group_by == "file":
            return resources[self._api]
        return _ResourceGroup(av, resources)

    def __dir__(self) -> list[str]:
        return sorted([*self._versions, "latest", "versions", "api", "version"])

    def __repr__(self) -> str:
        return f"<API {self._api}: versions {', '.join(self.versions)}>"


class _ResourceGroup:
    """Version with multiple resources (tag/path grouping)."""

    def __init__(self, av: APIVersion, resources: dict[str, Any]) -> None:
        self._av = av
        self._resources = resources
        self.models = av.models

    def __getattr__(self, name: str) -> Any:
        try:
            return self._resources[name]
        except KeyError:
            raise AttributeError(name) from None

    def __dir__(self) -> list[str]:
        return sorted([*self._resources, "models"])


class _ClientCore:
    """Shared state between ``Client`` and ``AsyncClient``: spec discovery,
    plugin list and compiled API cache."""

    is_async = False

    def __init__(
        self,
        specs: str | os.PathLike[str] | Iterable[str | os.PathLike[str]],
        *,
        plugins: Iterable[Any] = (),
        group_by: GroupBy = "file",
        use_cache: bool = True,
        enum_mode: Any = "literal",
    ) -> None:
        self.plugins = list(plugins)
        self.group_by: GroupBy = group_by
        self.use_cache = use_cache
        self.enum_mode = enum_mode
        self.runtime: Any = None
        self._apis: dict[str, dict[str, pathlib.Path]] = {}
        self._aliases: dict[str, str] = {}
        self._containers: dict[str, APIVersions] = {}
        self._discover(specs)

    def _discover(self, specs: Any) -> None:
        roots = [specs] if isinstance(specs, (str, os.PathLike)) else list(specs)
        files: list[pathlib.Path] = []
        for root in roots:
            root = pathlib.Path(root)
            found: Iterable[pathlib.Path] | None = None
            for plugin in self.plugins:
                hook = getattr(plugin, "spec_files", None)
                if hook is not None:
                    found = hook(root)
                    break
            files.extend(found if found is not None else default_spec_files(root))
        pending_version: list[tuple[str, pathlib.Path]] = []
        for path in files:
            named: tuple[str, str] | None = None
            for plugin in self.plugins:
                hook = getattr(plugin, "api_naming", None)
                if hook is not None:
                    named = hook(path)
                    if named is not None:
                        break
            if named is None:
                api, version = default_api_naming(path)
                if version is None:
                    pending_version.append((api, path))
                    continue
                named = (api, version)
            self._register(named[0], named[1], path)
        for api, path in pending_version:
            doc = load_document(path, use_cache=self.use_cache)
            self._register(api, normalize_version(doc.version), path)
        for plugin in self.plugins:
            hook = getattr(plugin, "aliases", None)
            if hook is not None:
                self._aliases.update({k: v for k, v in hook().items() if v in self._apis})

    def _register(self, api: str, version: str, path: pathlib.Path) -> None:
        versions = self._apis.setdefault(api, {})
        if version in versions and versions[version] != path:
            log.warning("spec %s and %s both map to %s.%s; keeping the first", versions[version], path, api, version)
            return
        versions[version] = path

    def api(self, name: str) -> APIVersions:
        canonical = self._aliases.get(name, name)
        container = self._containers.get(canonical)
        if container is None:
            versions = self._apis.get(canonical)
            if versions is None:
                raise AttributeError(f"no API named {name!r}; available: {', '.join(sorted(self._apis))}")
            container = APIVersions(self, canonical, versions)
            self._containers[canonical] = container
        return container

    @property
    def apis(self) -> list[str]:
        return sorted(self._apis)

    @property
    def aliases(self) -> dict[str, str]:
        return dict(self._aliases)

    def api_versions(self) -> dict[str, list[str]]:
        return {api: sorted(v, key=version_key) for api, v in self._apis.items()}

    def preload(self) -> dict[str, float]:
        """Load, compile and force-build every API; returns build time (ms) per key."""
        times: dict[str, float] = {}
        for api in self.apis:
            container = self.api(api)
            for version in container.versions:
                av = container.version(version)
                started = time.perf_counter()
                for op in av.operations:
                    op.warm()
                av.models.build_all()
                av.resources()
                times[av.key] = (time.perf_counter() - started) * 1000
        return times

    def compiled_versions(self) -> list[APIVersion]:
        return [c.version(v) for c in self._containers.values() for v in c.versions if c.version(v)._ops is not None]


class _AttrAccess:
    _core: _ClientCore

    def __getattr__(self, name: str) -> APIVersions:
        if name.startswith("_"):
            raise AttributeError(name)
        return self._core.api(name)

    def __dir__(self) -> list[str]:
        return sorted(set(self._core.apis) | set(self._core.aliases) | set(super().__dir__()))

    @property
    def apis(self) -> list[str]:
        return self._core.apis

    def api(self, name: str) -> APIVersions:
        return self._core.api(name)

    def preload(self) -> dict[str, float]:
        return self._core.preload()


def _client_kwargs(plugins: Iterable[Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for plugin in plugins:
        hook = getattr(plugin, "client_defaults", None)
        if hook is not None:
            merged.update(hook())
    merged.update(kwargs)
    return merged


class Client(SyncAPIClient, _AttrAccess):
    """Synchronous spec-driven client.

    Parameters
    ----------
    specs:
        A spec file, a directory of spec files, or an iterable of those.
    base_url:
        Server URL. When omitted, the first ``servers`` entry of the first
        loaded document is used lazily.
    plugins:
        Objects with ``annotate(document)`` (see ``spapi.plugins``).
    group_by:
        ``"file"`` (default), ``"tag"`` or ``"path_prefix"``.
    Remaining keyword arguments are ``SyncAPIClient`` options (timeouts,
    retries, ``http_client=``, ``transport=``, ``auth=``, ...).
    """

    def __init__(
        self,
        specs: str | os.PathLike[str] | Iterable[str | os.PathLike[str]],
        *,
        base_url: str | None = None,
        plugins: Iterable[Any] = (),
        group_by: GroupBy = "file",
        use_cache: bool = True,
        enum_mode: Any = "literal",
        **kwargs: Any,
    ) -> None:
        plugins = list(plugins)
        self._core = _ClientCore(specs, plugins=plugins, group_by=group_by, use_cache=use_cache, enum_mode=enum_mode)
        self._core.runtime = self
        super().__init__(base_url=base_url or "", **_client_kwargs(plugins, kwargs))
        self._lazy_base_url = base_url is None

    def _build_request(self, op: CompiledOp, kwargs: dict[str, Any], options: Any) -> Any:
        if self._lazy_base_url:
            self._resolve_base_url(op)
        return super()._build_request(op, kwargs, options)

    def _resolve_base_url(self, op: CompiledOp) -> None:
        for av in self._core.compiled_versions():
            if any(o is op for o in av.operations) and av.document.servers:
                self.set_base_url(av.document.servers[0].url)
                self._lazy_base_url = False
                return
        self._lazy_base_url = False


class AsyncClient(AsyncAPIClient, _AttrAccess):
    """Asynchronous spec-driven client; see ``Client``."""

    def __init__(
        self,
        specs: str | os.PathLike[str] | Iterable[str | os.PathLike[str]],
        *,
        base_url: str | None = None,
        plugins: Iterable[Any] = (),
        group_by: GroupBy = "file",
        use_cache: bool = True,
        enum_mode: Any = "literal",
        **kwargs: Any,
    ) -> None:
        plugins = list(plugins)
        self._core = _ClientCore(specs, plugins=plugins, group_by=group_by, use_cache=use_cache, enum_mode=enum_mode)
        self._core.is_async = True
        self._core.runtime = self
        super().__init__(base_url=base_url or "", **_client_kwargs(plugins, kwargs))
        self._lazy_base_url = base_url is None

    def _build_request(self, op: CompiledOp, kwargs: dict[str, Any], options: Any) -> Any:
        if self._lazy_base_url:
            Client._resolve_base_url(self, op)  # type: ignore[arg-type]
        return super()._build_request(op, kwargs, options)


def __getattr__(name: str) -> Any:
    if name in ("SellingPartner", "AsyncSellingPartner"):
        from .plugins.amazon_spapi import AsyncSellingPartner, SellingPartner

        return {"SellingPartner": SellingPartner, "AsyncSellingPartner": AsyncSellingPartner}[name]
    raise AttributeError(name)


__all__ = [
    "APIVersion",
    "APIVersions",
    "AsyncClient",
    "AsyncResource",
    "Client",
    "SyncResource",
    "default_api_naming",
    "normalize_version",
    "version_key",
]
