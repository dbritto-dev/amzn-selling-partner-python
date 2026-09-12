"""Typed notification payload models (generated from ``schemas/notifications/*.json``
into ``sdk.models.notifications.<schema>``)."""

from __future__ import annotations

import enum
import importlib
import pkgutil
import re
import typing
from collections.abc import Mapping
from typing import Any, cast

from pydantic import BaseModel
from pydantic_core import from_json

from ..._naming import snake_case

_PACKAGE = "amzn_selling_partner.sdk.models.notifications"
_VERSION_SUFFIX = re.compile(r"_\d{4}_\d{2}_\d{2}$")


def _literal_values(annotation: Any) -> list[str]:
    """Values of a ``Literal``/``str`` enum annotation (``None`` members dropped)."""
    origin = typing.get_origin(annotation)
    if origin is typing.Literal:
        return [str(a) for a in typing.get_args(annotation) if a is not None]
    if origin is not None:  # Optional[X], X | None
        out: list[str] = []
        for arg in typing.get_args(annotation):
            if arg is not type(None):
                out.extend(_literal_values(arg))
        return out
    if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
        return [str(m.value) for m in annotation]
    return []


def _root_of(module_name: str, package: Any) -> type[BaseModel] | None:
    """The model of a notification package that describes the whole message."""
    models: list[type[BaseModel]] = []
    for attr in cast(list[str], getattr(package, "__all__", [])):
        obj = getattr(package, attr, None)
        if isinstance(obj, type) and issubclass(obj, BaseModel):
            models.append(obj)
    for model in models:
        if {"notification_type", "payload"} <= set(model.model_fields):
            return model
    for model in models:  # e.g. a dangling-reference schema: an empty model named like the file
        if model.__name__ == module_name:
            return model
    return None


def _stem(module_name: str) -> str:
    """Package name -> schema file stem: ``ListingsItemIssuesChangeNotification_2023_12_13`` -> ``..._2023-12-13``."""
    m = re.search(r"_(\d{4})_(\d{2})_(\d{2})$", module_name)
    return f"{module_name[: m.start()]}_{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else module_name


class Notifications:
    """Registry of notification payload models.

    ``model("OrderChangeNotification")`` returns the pydantic class of that
    schema file; ``parse(data)`` picks the model from the ``NotificationType``
    (and ``PayloadVersion`` when several schema versions exist) of the message.
    """

    def __init__(self) -> None:
        package = importlib.import_module(_PACKAGE)
        self._roots: dict[str, type[BaseModel]] = {}  # schema file stem -> root model
        self._modules: dict[str, str] = {}  # schema file stem -> package name
        for info in pkgutil.iter_modules(package.__path__):
            module = importlib.import_module(f"{_PACKAGE}.{info.name}")
            root = _root_of(info.name, module)
            if root is None:
                continue
            stem = _stem(info.name)
            self._roots[stem] = root
            self._modules[stem] = info.name
        self._index: dict[tuple[str, str | None], str] | None = None

    @property
    def names(self) -> list[str]:
        return sorted(self._roots)

    def module(self, name: str) -> Any:
        """The generated models package of one schema file."""
        try:
            module_name = self._modules[name]
        except KeyError:
            raise KeyError(name) from None
        return importlib.import_module(f"{_PACKAGE}.{module_name}")

    def model(self, name: str) -> type[BaseModel]:
        try:
            return self._roots[name]
        except KeyError:
            raise KeyError(name) from None

    def _build_index(self) -> dict[tuple[str, str | None], str]:
        index: dict[tuple[str, str | None], str] = {}
        for name in self.names:
            model = self.model(name)
            fields = model.model_fields
            types = _literal_values(fields["notification_type"].annotation) if "notification_type" in fields else []
            if not types:
                base = _VERSION_SUFFIX.sub("", self._modules[name])
                types = [snake_case(base).removesuffix("_notification").upper()]
            versions: list[str | None] = list(_literal_values(fields["payload_version"].annotation)) if "payload_version" in fields else []
            if not versions:
                versions = [None]
            for t in types:
                for v in [*versions, None]:
                    index.setdefault((t, v), name)
        return index

    def model_for_type(self, notification_type: str, payload_version: str | None = None) -> type[BaseModel]:
        if self._index is None:
            self._index = self._build_index()
        name = self._index.get((notification_type, payload_version)) or self._index.get((notification_type, None))
        if name is None:
            raise KeyError(f"no notification schema for type {notification_type!r}")
        return self.model(name)

    def parse(self, data: bytes | str | Mapping[str, Any], *, notification_type: str | None = None) -> BaseModel:
        decoded: Any = data if isinstance(data, Mapping) else from_json(data)
        if not isinstance(decoded, Mapping):
            raise ValueError("notification payload must be a JSON object")
        payload = cast(Mapping[str, Any], decoded)
        nt: Any = notification_type or payload.get("NotificationType")
        if not isinstance(nt, str):
            raise ValueError("notification payload has no NotificationType")
        pv: Any = payload.get("PayloadVersion")
        model = self.model_for_type(nt, str(pv) if pv is not None else None)
        return model.model_validate(payload)


__all__ = ["Notifications"]
