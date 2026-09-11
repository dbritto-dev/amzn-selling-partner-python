"""Typed notification payload models (generated from ``schemas/notifications/*.json``)."""

from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import Any, cast

from pydantic import BaseModel
from pydantic_core import from_json


class Notifications:
    """Registry of notification payload models.

    ``model("OrderChangeNotification")`` returns the pydantic class for that
    schema file; ``parse(data)`` picks the model from the ``NotificationType``
    (and ``PayloadVersion`` when several schema versions exist) of the message.
    """

    _PACKAGE = "amzn_selling_partner.models.notification_payloads"

    def __init__(self) -> None:
        registry = importlib.import_module(self._PACKAGE)
        self._schemas: dict[str, tuple[str, str]] = registry.SCHEMAS
        self._index: dict[tuple[str, str | None], str] = registry.INDEX

    @property
    def names(self) -> list[str]:
        return sorted(self._schemas)

    def module(self, name: str) -> Any:
        """The generated models module of one schema file."""
        try:
            module_name, _root = self._schemas[name]
        except KeyError:
            raise KeyError(name) from None
        return importlib.import_module(f"{self._PACKAGE}.{module_name}")

    def model(self, name: str) -> type[BaseModel]:
        _module_name, root = self._schemas[name]
        model = getattr(self.module(name), root, None)
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            raise TypeError(f"notification schema {name!r} does not describe an object (got {model!r}); the schema file is probably broken")
        return model

    def model_for_type(self, notification_type: str, payload_version: str | None = None) -> type[BaseModel]:
        name = self._index.get((notification_type, payload_version)) or self._index.get((notification_type, None))
        if name is None:
            candidates = [n for (t, _v), n in self._index.items() if t == notification_type]
            if not candidates:
                raise KeyError(f"no notification schema for type {notification_type!r}")
            name = candidates[0]
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
