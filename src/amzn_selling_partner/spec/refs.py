"""``$ref`` resolution for JSON documents.

``RefResolver`` loads sibling files on demand (relative refs within a directory
or URL prefix), evaluates JSON pointers over the decoded documents, and hands
the resolved nodes back validated as the requested pydantic model.
"""

from __future__ import annotations

import pathlib
import posixpath
from collections.abc import Callable, Mapping
from typing import Any, TypeVar, cast
from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ValidationError
from pydantic_core import from_json

from .raw import RawSchema

M = TypeVar("M", bound=BaseModel)


class RefError(ValueError):
    pass


def json_pointer(document: Any, pointer: str) -> Any:
    """Evaluate an RFC 6901 pointer (``/a/b/0``) against a decoded JSON value."""
    if pointer in ("", "/"):
        return document
    node: Any = document
    for raw in pointer.lstrip("/").split("/"):
        token = unquote(raw).replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            items = cast(list[Any], node)
            try:
                node = items[int(token)]
            except (ValueError, IndexError) as exc:
                raise RefError(f"bad pointer segment {token!r} in {pointer!r}") from exc
        elif isinstance(node, Mapping):
            mapping = cast(Mapping[str, Any], node)
            if token not in mapping:
                raise RefError(f"pointer {pointer!r} not found (missing {token!r})")
            node = mapping[token]
        else:
            raise RefError(f"cannot descend into {type(node).__name__} at {token!r}")
    return node


def read_json_file(path: str) -> Any:
    return from_json(pathlib.Path(path).read_bytes())


class RefResolver:
    """Resolves ``$ref`` strings relative to a root document.

    Parameters
    ----------
    root_uri:
        Location of the root document (a filesystem path or URL). Relative refs
        are resolved against its directory.
    root:
        The decoded root document.
    reader:
        Callable used to fetch other documents by resolved location.
    """

    def __init__(self, root_uri: str, root: Any, *, reader: Callable[[str], Any] = read_json_file) -> None:
        self.root_uri = root_uri
        self.documents: dict[str, Any] = {root_uri: root}
        self._reader = reader

    def split(self, ref: str, base_uri: str) -> tuple[str, str]:
        """Return ``(document uri, pointer)`` for ``ref`` seen from ``base_uri``."""
        target, _, fragment = ref.partition("#")
        if not target:
            return base_uri, fragment
        if urlsplit(target).scheme:
            return target, fragment
        base_dir = posixpath.dirname(base_uri.replace("\\", "/"))
        return posixpath.normpath(posixpath.join(base_dir, target)), fragment

    def document(self, uri: str) -> Any:
        doc = self.documents.get(uri)
        if doc is None:
            doc = self._reader(uri)
            self.documents[uri] = doc
        return doc

    def lookup(self, ref: str, base_uri: str) -> tuple[Any, str]:
        """Return ``(node, document uri)`` the reference points at."""
        uri, pointer = self.split(ref, base_uri)
        try:
            return json_pointer(self.document(uri), pointer), uri
        except RefError as exc:
            raise RefError(f"cannot resolve {ref!r} from {base_uri!r}: {exc}") from exc

    def lookup_model(self, ref: str, base_uri: str, model: type[M]) -> tuple[M, str]:
        """Resolve ``ref`` and validate the node as ``model``."""
        node, uri = self.lookup(ref, base_uri)
        try:
            return model.model_validate(node), uri
        except ValidationError as exc:
            raise RefError(f"$ref {ref!r} does not point at a valid {model.__name__}: {exc}") from exc

    def lookup_schema(self, ref: str, base_uri: str) -> tuple[RawSchema | bool, str]:
        node, uri = self.lookup(ref, base_uri)
        if isinstance(node, bool):
            return node, uri
        return self.lookup_model(ref, base_uri, RawSchema)[0], uri

    def is_local(self, ref: str, base_uri: str) -> bool:
        return self.split(ref, base_uri)[0] == base_uri


__all__ = ["RefError", "RefResolver", "json_pointer", "read_json_file"]
