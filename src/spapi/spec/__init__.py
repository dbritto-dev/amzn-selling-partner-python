"""Spec loading and normalisation into the intermediate representation (IR)."""

from .ir import (
    Discriminator,
    Document,
    Operation,
    Parameter,
    RequestBody,
    Response,
    Schema,
    Server,
)
from .loader import load_document, load_documents

__all__ = [
    "Discriminator",
    "Document",
    "Operation",
    "Parameter",
    "RequestBody",
    "Response",
    "Schema",
    "Server",
    "load_document",
    "load_documents",
]
