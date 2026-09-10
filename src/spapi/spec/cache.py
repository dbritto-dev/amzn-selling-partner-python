"""On-disk cache of loaded IR documents, keyed by the spec file hash.

Only IR (plain dataclasses) is pickled, never pydantic classes. The cache
directory defaults to ``$SPAPI_CACHE_DIR`` or ``~/.cache/spapi/ir``; set
``SPAPI_CACHE_DIR=`` (empty) to disable caching.
"""

from __future__ import annotations

import hashlib
import logging
import os
import pathlib
import pickle
import tempfile

from .ir import Document

log = logging.getLogger("spapi.spec.cache")

#: Bump whenever the IR or the normalisers change shape so stale pickles are ignored.
IR_VERSION = "1"


def spec_hash(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(IR_VERSION.encode())
    h.update(b"\0")
    h.update(data)
    return h.hexdigest()


def cache_dir() -> pathlib.Path | None:
    env = os.environ.get("SPAPI_CACHE_DIR")
    if env is not None:
        return pathlib.Path(env) if env else None
    return pathlib.Path.home() / ".cache" / "spapi" / "ir"


def cache_path(digest: str) -> pathlib.Path | None:
    base = cache_dir()
    return None if base is None else base / f"{digest}.pickle"


def load_cached(digest: str) -> Document | None:
    path = cache_path(digest)
    if path is None:
        return None
    try:
        with path.open("rb") as fh:
            doc = pickle.load(fh)  # noqa: S301 - our own cache directory
    except FileNotFoundError:
        return None
    except (OSError, pickle.UnpicklingError, EOFError, AttributeError, ImportError) as exc:
        log.warning("ignoring unreadable IR cache entry %s: %s", path, exc)
        return None
    if not isinstance(doc, Document):
        return None
    return doc


def store_cached(digest: str, document: Document) -> None:
    path = cache_path(digest)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=".pickle")
        with os.fdopen(fd, "wb") as fh:
            pickle.dump(document, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
    except OSError as exc:
        log.warning("could not write IR cache entry %s: %s", path, exc)


__all__ = ["IR_VERSION", "cache_dir", "load_cached", "spec_hash", "store_cached"]
