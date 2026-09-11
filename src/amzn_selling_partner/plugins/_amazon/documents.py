"""Feed and report document helpers: pre-signed URL download (gzip aware,
optionally streamed to a file) and upload, sync and async."""

from __future__ import annotations

import gzip
import os
import zlib
from collections.abc import AsyncIterator, Iterator
from typing import Any, cast

import httpx2

from ...runtime._errors import APIConnectionError, status_error_class
from .rdt import RESTRICTED_REPORT_TYPES

CHUNK = 64 * 1024


def _check(response: httpx2.Response, what: str) -> None:
    if response.status_code >= 400:
        cls = status_error_class(response.status_code)
        raise cls(f"{what} failed with HTTP {response.status_code}", response=response, body=response.content)


def _needs_gunzip(response: httpx2.Response, compression: str | None) -> bool:
    return (compression or "").upper() == "GZIP" and "gzip" not in response.headers.get("content-encoding", "").lower()


def _gunzip_stream(chunks: Iterator[bytes]) -> Iterator[bytes]:
    d = zlib.decompressobj(wbits=31)
    for chunk in chunks:
        out = d.decompress(chunk)
        if out:
            yield out
    tail = d.flush()
    if tail:
        yield tail


async def _agunzip_stream(chunks: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    d = zlib.decompressobj(wbits=31)
    async for chunk in chunks:
        out = d.decompress(chunk)
        if out:
            yield out
    tail = d.flush()
    if tail:
        yield tail


# -- sync ------------------------------------------------------------------------------


def download_document(url: str, *, compression: str | None = None, http_client: httpx2.Client | None = None) -> bytes:
    """Fetch a pre-signed document URL and return the decompressed bytes."""
    client = http_client or httpx2.Client(timeout=httpx2.Timeout(120.0, connect=10.0))
    try:
        try:
            response = client.get(url)
        except httpx2.TransportError as exc:
            raise APIConnectionError(f"document download failed: {exc}", cause=exc) from exc
        _check(response, "document download")
        data = response.content
        return gzip.decompress(data) if _needs_gunzip(response, compression) else data
    finally:
        if http_client is None:
            client.close()


def download_document_to_file(
    url: str,
    path: str | os.PathLike[str],
    *,
    compression: str | None = None,
    http_client: httpx2.Client | None = None,
    chunk_size: int = CHUNK,
) -> int:
    """Stream a document to ``path`` (decompressing gzip on the fly); returns bytes written."""
    client = http_client or httpx2.Client(timeout=httpx2.Timeout(120.0, connect=10.0))
    written = 0
    try:
        try:
            with client.stream("GET", url) as response:
                if response.status_code >= 400:
                    response.read()
                    _check(response, "document download")
                chunks: Iterator[bytes] = response.iter_bytes(chunk_size)
                if _needs_gunzip(response, compression):
                    chunks = _gunzip_stream(chunks)
                with open(path, "wb") as fh:
                    for chunk in chunks:
                        fh.write(chunk)
                        written += len(chunk)
        except httpx2.TransportError as exc:
            raise APIConnectionError(f"document download failed: {exc}", cause=exc) from exc
    finally:
        if http_client is None:
            client.close()
    return written


def upload_document(url: str, content: bytes | str, *, content_type: str, http_client: httpx2.Client | None = None) -> None:
    """PUT ``content`` to a pre-signed upload URL. ``content_type`` must equal
    the value used when the document was created."""
    client = http_client or httpx2.Client(timeout=httpx2.Timeout(120.0, connect=10.0))
    try:
        body = content.encode() if isinstance(content, str) else content
        try:
            response = client.put(url, content=body, headers={"Content-Type": content_type})
        except httpx2.TransportError as exc:
            raise APIConnectionError(f"document upload failed: {exc}", cause=exc) from exc
        _check(response, "document upload")
    finally:
        if http_client is None:
            client.close()


# -- async -------------------------------------------------------------------------------


async def async_download_document(url: str, *, compression: str | None = None, http_client: httpx2.AsyncClient | None = None) -> bytes:
    client = http_client or httpx2.AsyncClient(timeout=httpx2.Timeout(120.0, connect=10.0))
    try:
        try:
            response = await client.get(url)
        except httpx2.TransportError as exc:
            raise APIConnectionError(f"document download failed: {exc}", cause=exc) from exc
        _check(response, "document download")
        data = response.content
        return gzip.decompress(data) if _needs_gunzip(response, compression) else data
    finally:
        if http_client is None:
            await client.aclose()


async def async_download_document_to_file(
    url: str,
    path: str | os.PathLike[str],
    *,
    compression: str | None = None,
    http_client: httpx2.AsyncClient | None = None,
    chunk_size: int = CHUNK,
) -> int:
    client = http_client or httpx2.AsyncClient(timeout=httpx2.Timeout(120.0, connect=10.0))
    written = 0
    try:
        try:
            async with client.stream("GET", url) as response:
                if response.status_code >= 400:
                    await response.aread()
                    _check(response, "document download")
                chunks: AsyncIterator[bytes] = response.aiter_bytes(chunk_size)
                if _needs_gunzip(response, compression):
                    chunks = _agunzip_stream(chunks)
                with open(path, "wb") as fh:
                    async for chunk in chunks:
                        fh.write(chunk)
                        written += len(chunk)
        except httpx2.TransportError as exc:
            raise APIConnectionError(f"document download failed: {exc}", cause=exc) from exc
    finally:
        if http_client is None:
            await client.aclose()
    return written


async def async_upload_document(
    url: str, content: bytes | str, *, content_type: str, http_client: httpx2.AsyncClient | None = None
) -> None:
    client = http_client or httpx2.AsyncClient(timeout=httpx2.Timeout(120.0, connect=10.0))
    try:
        body = content.encode() if isinstance(content, str) else content
        try:
            response = await client.put(url, content=body, headers={"Content-Type": content_type})
        except httpx2.TransportError as exc:
            raise APIConnectionError(f"document upload failed: {exc}", cause=exc) from exc
        _check(response, "document upload")
    finally:
        if http_client is None:
            await client.aclose()


# -- client-bound helpers -------------------------------------------------------------------


def _doc_fields(document: Any) -> tuple[str, str | None]:
    if isinstance(document, dict):
        d = cast(dict[str, Any], document)
        compression: Any = d.get("compressionAlgorithm")
        return str(d["url"]), str(compression) if compression is not None else None
    return str(document.url), getattr(document, "compression_algorithm", None)


def _url_and_id(doc: Any) -> tuple[str, str]:
    if isinstance(doc, dict):
        d = cast(dict[str, Any], doc)
        return str(d["url"]), str(d["feedDocumentId"])
    return str(doc.url), str(doc.feed_document_id)


def _rdt_options(report_type: str | None) -> Any:
    from ...runtime._types import RequestOptions

    if report_type and report_type in RESTRICTED_REPORT_TYPES:
        return RequestOptions(auth={"rdt": True})
    return None


class Documents:
    """``client.documents``: report/feed document workflows over the bound client."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get_report_document(self, report_document_id: str, *, report_type: str | None = None) -> Any:
        return self._client.reports.latest.get_report_document(
            report_document_id=report_document_id, request_options=_rdt_options(report_type)
        )

    def download_report(
        self, report_document_id: str, *, report_type: str | None = None, path: str | os.PathLike[str] | None = None
    ) -> bytes | int:
        doc = self.get_report_document(report_document_id, report_type=report_type)
        url, compression = _doc_fields(doc)
        http = self._client.http_client
        if path is not None:
            return download_document_to_file(url, path, compression=compression, http_client=http)
        return download_document(url, compression=compression, http_client=http)

    def download_feed_result(self, feed_document_id: str, *, path: str | os.PathLike[str] | None = None) -> bytes | int:
        doc = self._client.feeds.latest.get_feed_document(feed_document_id=feed_document_id)
        url, compression = _doc_fields(doc)
        http = self._client.http_client
        if path is not None:
            return download_document_to_file(url, path, compression=compression, http_client=http)
        return download_document(url, compression=compression, http_client=http)

    def upload_feed_document(self, content: bytes | str, *, content_type: str) -> str:
        """Create a feed document, upload ``content`` and return the feedDocumentId."""
        doc = self._client.feeds.latest.create_feed_document(body={"contentType": content_type})
        url, document_id = _url_and_id(doc)
        upload_document(url, content, content_type=content_type, http_client=self._client.http_client)
        return document_id

    def create_feed(
        self,
        feed_type: str,
        marketplace_ids: list[str],
        content: bytes | str,
        *,
        content_type: str,
        feed_options: dict[str, str] | None = None,
    ) -> Any:
        """Upload ``content`` and create the feed; returns the createFeed response."""
        document_id = self.upload_feed_document(content, content_type=content_type)
        body: dict[str, Any] = {"feedType": feed_type, "marketplaceIds": marketplace_ids, "inputFeedDocumentId": document_id}
        if feed_options:
            body["feedOptions"] = feed_options
        return self._client.feeds.latest.create_feed(body=body)


class AsyncDocuments:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def get_report_document(self, report_document_id: str, *, report_type: str | None = None) -> Any:
        return await self._client.reports.latest.get_report_document(
            report_document_id=report_document_id, request_options=_rdt_options(report_type)
        )

    async def download_report(
        self, report_document_id: str, *, report_type: str | None = None, path: str | os.PathLike[str] | None = None
    ) -> bytes | int:
        doc = await self.get_report_document(report_document_id, report_type=report_type)
        url, compression = _doc_fields(doc)
        http = self._client.http_client
        if path is not None:
            return await async_download_document_to_file(url, path, compression=compression, http_client=http)
        return await async_download_document(url, compression=compression, http_client=http)

    async def download_feed_result(self, feed_document_id: str, *, path: str | os.PathLike[str] | None = None) -> bytes | int:
        doc = await self._client.feeds.latest.get_feed_document(feed_document_id=feed_document_id)
        url, compression = _doc_fields(doc)
        http = self._client.http_client
        if path is not None:
            return await async_download_document_to_file(url, path, compression=compression, http_client=http)
        return await async_download_document(url, compression=compression, http_client=http)

    async def upload_feed_document(self, content: bytes | str, *, content_type: str) -> str:
        doc = await self._client.feeds.latest.create_feed_document(body={"contentType": content_type})
        url, document_id = _url_and_id(doc)
        await async_upload_document(url, content, content_type=content_type, http_client=self._client.http_client)
        return document_id

    async def create_feed(
        self,
        feed_type: str,
        marketplace_ids: list[str],
        content: bytes | str,
        *,
        content_type: str,
        feed_options: dict[str, str] | None = None,
    ) -> Any:
        document_id = await self.upload_feed_document(content, content_type=content_type)
        body: dict[str, Any] = {"feedType": feed_type, "marketplaceIds": marketplace_ids, "inputFeedDocumentId": document_id}
        if feed_options:
            body["feedOptions"] = feed_options
        return await self._client.feeds.latest.create_feed(body=body)


__all__ = [
    "AsyncDocuments",
    "Documents",
    "async_download_document",
    "async_download_document_to_file",
    "async_upload_document",
    "download_document",
    "download_document_to_file",
    "upload_document",
]
