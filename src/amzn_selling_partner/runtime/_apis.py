"""Base classes behind the generated ``apis.py`` (typed, lazily imported API
containers): ``client.orders`` -> ``APIVersionsBase`` subclass, ``.v0`` ->
resource instance created on first access and cached per client."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from ._resources import AsyncResource, SyncResource


class APIVersionsBase:
    """``client.<api>``: one attribute per version plus ``latest`` / ``versions``."""

    __slots__ = ("_cache", "_client")

    _api: ClassVar[str] = ""
    _versions: ClassVar[tuple[str, ...]] = ()
    _latest: ClassVar[str] = ""
    _is_async: ClassVar[bool] = False

    def __init__(self, client: Any) -> None:
        self._client = client
        self._cache: dict[str, Any] = {}

    @property
    def api(self) -> str:
        return self._api

    @property
    def versions(self) -> list[str]:
        return list(self._versions)

    def _get(self, version: str) -> Any:
        res = self._cache.get(version)
        if res is None:
            if version not in self._versions:
                raise AttributeError(f"API {self._api!r} has no version {version!r}; available: {', '.join(self._versions)}")
            package = self._client._package  # pyright: ignore[reportPrivateUsage]
            module = importlib.import_module(f"{package}.resources.{self._api}.{version}")
            cls_name = module.__all__[0] if self._is_async else module.__all__[1]
            res = getattr(module, cls_name)(self._client)
            self._cache[version] = res
        return res

    def version(self, name: str) -> Any:
        """Resource for ``name`` (``"v0"``, ``"latest"``)."""
        return self._get(self._latest if name == "latest" else name)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return self._get(name)

    def __dir__(self) -> list[str]:
        return sorted([*self._versions, "latest", "versions", "api", "version"])

    def __repr__(self) -> str:
        return f"<API {self._api}: versions {', '.join(self._versions)}>"


class _APIsBase:
    """Mixin for the clients: ``client.<api>`` containers, cached per client."""

    __slots__ = ()

    _package: ClassVar[str] = ""
    _api_containers: dict[str, Any]

    def _api_container(self, name: str, cls: type[APIVersionsBase]) -> Any:
        containers: dict[str, APIVersionsBase] | None = self.__dict__.get("_api_containers")
        if containers is None:
            containers = {}
            self.__dict__["_api_containers"] = containers
        c: APIVersionsBase | None = containers.get(name)
        if c is None:
            c = cls(self)
            containers[name] = c
        return c

    def api(self, name: str) -> Any:
        """``client.api("orders")`` (aliases accepted)."""
        registry = importlib.import_module(f"{self._package}.apis")
        canonical = registry.ALIASES.get(name, name)
        if canonical not in registry.API_VERSIONS:
            raise AttributeError(f"no API named {name!r}; available: {', '.join(sorted(registry.API_VERSIONS))}")
        return getattr(self, canonical)

    @property
    def apis(self) -> list[str]:
        registry = importlib.import_module(f"{self._package}.apis")
        return sorted(registry.API_VERSIONS)

    @property
    def aliases(self) -> dict[str, str]:
        registry = importlib.import_module(f"{self._package}.apis")
        return dict(registry.ALIASES)

    def api_versions(self) -> dict[str, list[str]]:
        registry = importlib.import_module(f"{self._package}.apis")
        return {api: list(v) for api, v in registry.API_VERSIONS.items()}

    def preload(self) -> dict[str, float]:
        """Import every API version and build its adapters; returns ms per version."""
        import time

        times: dict[str, float] = {}
        for api, versions in self.api_versions().items():
            container = getattr(self, api)
            for version in versions:
                started = time.perf_counter()
                res: SyncResource | AsyncResource = container.version(version)
                res.warm()
                times[f"{api}.{version}"] = (time.perf_counter() - started) * 1000
        return times


class SyncAPIsBase(_APIsBase):
    __slots__ = ()


class AsyncAPIsBase(_APIsBase):
    __slots__ = ()


__all__ = ["APIVersionsBase", "AsyncAPIsBase", "SyncAPIsBase"]
