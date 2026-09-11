"""Typed notification models built from ``schemas/notifications/*.json``."""

from __future__ import annotations

import pathlib
import threading
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel
from pydantic_core import from_json

from ...compile.models import ModelNamespace, build_models
from ...spec._jsonutil import as_object
from ...spec.loader import load_document


class Notifications:
    """Lazy registry of notification payload models.

    ``model("OrderChangeNotification")`` returns the pydantic class for that
    schema file; ``parse(data)`` picks the model from the ``NotificationType``
    (and ``PayloadVersion`` when several schema versions exist) of the message.
    """

    def __init__(self, schema_dir: str | pathlib.Path, *, use_cache: bool = True) -> None:
        self.schema_dir = pathlib.Path(schema_dir)
        self.use_cache = use_cache
        self._namespaces: dict[str, ModelNamespace] = {}
        self._by_type: dict[tuple[str, str | None], str] | None = None
        self._lock = threading.RLock()

    @property
    def names(self) -> list[str]:
        return sorted(p.stem for p in self.schema_dir.glob("*.json"))

    def namespace(self, name: str) -> ModelNamespace:
        ns = self._namespaces.get(name)
        if ns is None:
            with self._lock:
                ns = self._namespaces.get(name)
                if ns is None:
                    path = self.schema_dir / f"{name}.json"
                    if not path.exists():
                        raise KeyError(name)
                    doc = load_document(path, use_cache=self.use_cache)
                    ns = build_models(doc, key=f"notifications.{name}")
                    self._namespaces[name] = ns
        return ns

    def model(self, name: str) -> type[BaseModel]:
        ns = self.namespace(name)
        root = ns.document.annotations["root_schema"]
        model = ns.get(root)
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            raise TypeError(f"notification schema {name!r} does not describe an object (got {model!r}); the schema file is probably broken")
        return model

    def _index(self) -> dict[tuple[str, str | None], str]:
        if self._by_type is None:
            with self._lock:
                if self._by_type is None:
                    index: dict[tuple[str, str | None], str] = {}
                    for name in self.names:
                        doc = load_document(self.schema_dir / f"{name}.json", use_cache=self.use_cache)
                        root = doc.schemas[doc.annotations["root_schema"]]
                        nt = root.properties.get("NotificationType")
                        pv = root.properties.get("PayloadVersion")
                        types: list[Any] = list(nt.enum or ()) if nt else []
                        if nt is not None and nt.has_const:
                            types.append(nt.const)
                        if nt is not None and not types and isinstance(nt.example, str):
                            types.append(nt.example)
                        versions: list[str | None] = [None]
                        if pv is not None and (pv.enum or pv.has_const):
                            versions = [str(v) for v in (pv.enum or (pv.const,))]
                        elif pv is not None and isinstance(pv.example, str):
                            versions = [pv.example, None]
                        for t in types:
                            for v in versions:
                                index.setdefault((str(t), v), name)
                    self._by_type = index
        return self._by_type

    def model_for_type(self, notification_type: str, payload_version: str | None = None) -> type[BaseModel]:
        index = self._index()
        name = index.get((notification_type, payload_version)) or index.get((notification_type, None))
        if name is None:
            candidates = [n for (t, _v), n in index.items() if t == notification_type]
            if not candidates:
                raise KeyError(f"no notification schema for type {notification_type!r}")
            name = candidates[0]
        return self.model(name)

    def parse(self, data: bytes | str | Mapping[str, Any], *, notification_type: str | None = None) -> BaseModel:
        decoded: Any = data if isinstance(data, Mapping) else from_json(data)
        payload = as_object(decoded)
        if payload is None:
            raise ValueError("notification payload must be a JSON object")
        nt: Any = notification_type or payload.get("NotificationType")
        if not isinstance(nt, str):
            raise ValueError("notification payload has no NotificationType")
        pv: Any = payload.get("PayloadVersion")
        model = self.model_for_type(nt, str(pv) if pv is not None else None)
        return model.model_validate(payload)


__all__ = ["Notifications"]
