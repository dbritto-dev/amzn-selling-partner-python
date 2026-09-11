"""Plugin interface.

A plugin is any object with ``annotate(document) -> document``; it runs after a
document is loaded (and after the IR cache), before compilation. Plugins carry
all API-specific knowledge: servers, rate limits, pagination overrides, auth
requirements, naming of API attributes. Optional hooks are looked up with
``getattr`` so a plain object with only ``annotate`` is a valid plugin.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Iterable, Mapping
from typing import Any, Protocol, runtime_checkable

from ..spec.ir import Document


@runtime_checkable
class Plugin(Protocol):
    def annotate(self, document: Document) -> Document: ...


class OptionalHooks(Protocol):
    """Documented optional plugin hooks (all may be absent)."""

    def spec_files(self, root: pathlib.Path) -> Iterable[pathlib.Path]:
        """Which files under ``root`` are API specs (default: ``**/*.json``)."""
        ...

    def api_naming(self, path: pathlib.Path) -> tuple[str, str] | None:
        """``(api_name, version)`` for a spec file, or ``None`` to use the default."""
        ...

    def aliases(self) -> Mapping[str, str]:
        """Extra attribute names -> canonical API names."""
        ...

    def client_defaults(self) -> Mapping[str, Any]:
        """Extra keyword defaults for the runtime client (e.g. headers)."""
        ...


def run_plugins(document: Document, plugins: Iterable[Any]) -> Document:
    for plugin in plugins:
        result: object = plugin.annotate(document)
        if not isinstance(result, Document):
            raise TypeError(f"{type(plugin).__name__}.annotate() must return a Document")
        document = result
    return document


def default_spec_files(root: pathlib.Path | str | os.PathLike[str]) -> list[pathlib.Path]:
    root = pathlib.Path(root)
    if root.is_file():
        return [root]
    return sorted(p for p in root.glob("**/*.json") if not p.name.endswith(".example.json"))


__all__ = ["OptionalHooks", "Plugin", "default_spec_files", "run_plugins"]
