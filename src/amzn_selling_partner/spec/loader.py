"""Entry points: ``load_document`` / ``load_documents``.

A document is read from disk, hashed, looked up in the IR cache and otherwise
normalised (Swagger 2.0, OpenAPI 3.x, or a bare JSON Schema file such as the
Amazon notification payload schemas). Plugins are *not* applied here: they are
the client's concern and their output must not be cached.
"""

from __future__ import annotations

import logging
import os
import pathlib
import re
import time
from collections.abc import Iterable

from pydantic_core import from_json

from ._jsonutil import JsonObject, as_object
from ._schema import SchemaConverter
from .cache import load_cached, spec_hash, store_cached
from .ir import Document
from .openapi3 import normalize_openapi3
from .raw import RawSchema
from .refs import RefResolver
from .swagger2 import normalize_swagger2

log = logging.getLogger("amzn_selling_partner.spec")


def normalize(raw: JsonObject, *, source: str, digest: str) -> Document:
    if "swagger" in raw:
        return normalize_swagger2(raw, source=source, digest=digest)
    if "openapi" in raw:
        return normalize_openapi3(raw, source=source, digest=digest)
    return normalize_jsonschema(raw, source=source, digest=digest)


def normalize_jsonschema(raw: JsonObject, *, source: str, digest: str) -> Document:
    """A standalone JSON Schema becomes a document with one root schema (named
    after the file stem) plus its ``definitions`` / ``$defs``."""
    root = RawSchema.model_validate(raw)
    resolver = RefResolver(source, raw)
    conv = SchemaConverter(resolver)
    conv.register_all(root.definitions or {}, source, "/definitions")
    conv.register_all(root.defs or {}, source, "/$defs")
    stem = pathlib.Path(source).stem
    name = re.sub(r"[^0-9A-Za-z_]", "_", stem) or "Root"
    if name in conv.schemas:
        name = f"{name}Root"
    conv.schemas[name] = conv.convert(root, source, name=name)
    return Document(
        title=name,
        version=str(raw.get("version") or ""),
        format="jsonschema",
        source=source,
        hash=digest,
        description=root.description,
        schemas=dict(conv.schemas),
        extensions=root.extensions,
        annotations={"root_schema": name},
    )


def load_document(path: str | os.PathLike[str], *, use_cache: bool = True) -> Document:
    """Load one spec file into IR, using the on-disk cache when possible."""
    p = pathlib.Path(path)
    data = p.read_bytes()
    digest = spec_hash(data)
    if use_cache:
        cached = load_cached(digest)
        if cached is not None:
            log.debug("IR cache hit for %s", p)
            return cached
    started = time.perf_counter()
    raw = as_object(from_json(data))
    if raw is None:
        raise ValueError(f"{p}: top level of a spec must be a JSON object")
    doc = normalize(raw, source=str(p), digest=digest)
    log.debug(
        "normalised %s (%s, %d operations, %d schemas) in %.1f ms",
        p,
        doc.format,
        len(doc.operations),
        len(doc.schemas),
        (time.perf_counter() - started) * 1000,
    )
    if use_cache:
        store_cached(digest, doc)
    return doc


def load_documents(paths: Iterable[str | os.PathLike[str]], *, use_cache: bool = True) -> list[Document]:
    return [load_document(p, use_cache=use_cache) for p in paths]


__all__ = ["load_document", "load_documents", "normalize", "normalize_jsonschema"]
