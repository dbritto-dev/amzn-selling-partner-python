import gzip
import json
import typing
from functools import cached_property

import httpx2

from .. import _base_client, utils
from . import models

if typing.TYPE_CHECKING:
    from .._client import AsyncClient

_RESOURCE_PATH = "reports/2021-06-30"


class AsyncReports:
    def __init__(self, client: "AsyncClient") -> None:
        self._client = client

    async def _create_report_response(
        self, data: models.CreateReportSpecification
    ) -> httpx2.Response:
        body = data.model_dump_json(exclude_none=True).encode("utf-8")
        return await self._client._request(
            _base_client.RequestOptions(
                method="POST", url=f"{_RESOURCE_PATH}/reports", content=body
            )
        )

    async def create_report(self, data: models.CreateReportSpecification) -> models.Report:
        response = await self._create_report_response(data)
        report_id = models.CreateReportResponse.model_validate_json(response.content).reportId
        return await self.get_report(report_id)

    async def _get_reports_response(
        self, *, query: typing.Optional[models.GetReportsQuery] = None
    ) -> httpx2.Response:
        return await self._client._request(
            _base_client.RequestOptions(
                method="GET",
                url=f"{_RESOURCE_PATH}/reports",
                params=query.model_dump(exclude_none=True) if query is not None else None,
                rate_limit_sleep=True,
            )
        )

    async def get_reports(
        self, *, query: typing.Optional[models.GetReportsQuery] = None, pages_limit: int = 3
    ) -> typing.List[models.Report]:
        reports: typing.List[models.Report] = []
        current_query = query
        remaining = pages_limit

        while True:
            response = await self._get_reports_response(query=current_query)
            data = models.GetReportsResponse.model_validate_json(response.content)
            reports.extend(data.reports)
            remaining -= 1

            if data.nextToken is None or remaining < 1:
                break

            current_query = models.GetReportsQuery()
            current_query.nextToken = data.nextToken

        return reports

    async def _get_report_response(self, report_id: str) -> httpx2.Response:
        return await self._client._request(
            _base_client.RequestOptions(method="GET", url=f"{_RESOURCE_PATH}/reports/{report_id}")
        )

    async def get_report(self, report_id: str) -> models.Report:
        if not report_id or not isinstance(report_id, str):
            raise ValueError(f"report_id must be a string present but found `{report_id}`")

        response = await self._get_report_response(report_id)
        return models.Report.model_validate_json(response.content)

    async def _get_report_document_response(
        self,
        report_document_id: str,
        *,
        enable_content_encoding_url_header: typing.Optional[bool] = None,
    ) -> httpx2.Response:
        return await self._client._request(
            _base_client.RequestOptions(
                method="GET",
                url=f"{_RESOURCE_PATH}/documents/{report_document_id}",
                params=(
                    {
                        "enableContentEncodingUrlHeader": (
                            str(enable_content_encoding_url_header).lower()
                        ),
                    }
                    if enable_content_encoding_url_header is not None
                    else None
                ),
            )
        )

    async def get_report_document(
        self,
        report_document_id: str,
        *,
        enable_content_encoding_url_header: typing.Optional[bool] = None,
    ) -> models.ReportDocument:
        if not report_document_id or not isinstance(report_document_id, str):
            raise ValueError(
                f"report_document_id must be a string present but found `{report_document_id}`"
            )

        response = await self._get_report_document_response(
            report_document_id,
            enable_content_encoding_url_header=enable_content_encoding_url_header,
        )
        return models.ReportDocument.model_validate_json(response.content)

    async def _get_report_document_raw_content(
        self,
        report_document_id: str,
        *,
        enable_content_encoding_url_header: typing.Optional[bool] = None,
    ) -> bytes:
        report_document = await self.get_report_document(
            report_document_id,
            enable_content_encoding_url_header=enable_content_encoding_url_header,
        )
        download_response = await self._client._request(
            _base_client.RequestOptions(method="GET", url=report_document.url, auth=None)
        )
        if (
            report_document.compressionAlgorithm == models.CompressionAlgorithm.GZIP
            and download_response.headers.get("Content-Encoding", "").lower() != "gzip"
        ):
            return gzip.decompress(download_response.content)
        return download_response.content

    async def _get_report_document_content(
        self,
        report_document_id: str,
        *,
        enable_content_encoding_url_header: typing.Optional[bool] = None,
    ) -> typing.Dict:
        raw_content = await self._get_report_document_raw_content(
            report_document_id,
            enable_content_encoding_url_header=enable_content_encoding_url_header,
        )
        return json.loads(raw_content)

    async def get_report_document_content(
        self,
        report_document_id: str,
        *,
        enable_content_encoding_url_header: typing.Optional[bool] = None,
    ) -> typing.Dict:
        if not report_document_id or not isinstance(report_document_id, str):
            raise ValueError(
                f"report_document_id must be a string present but found `{report_document_id}`"
            )

        return await self._get_report_document_content(
            report_document_id,
            enable_content_encoding_url_header=enable_content_encoding_url_header,
        )

    async def download_report_document_content(
        self,
        report_document_id: str,
        file_path: str,
        *,
        enable_content_encoding_url_header: typing.Optional[bool] = None,
    ) -> None:
        if not report_document_id or not isinstance(report_document_id, str):
            raise ValueError(
                f"report_document_id must be a string present but found `{report_document_id}`"
            )

        if not file_path or not isinstance(file_path, str):
            raise ValueError(f"file_path must be a string present but found `{file_path}`")

        utils.file.write_binary_file(
            file_path,
            await self._get_report_document_raw_content(
                report_document_id,
                enable_content_encoding_url_header=enable_content_encoding_url_header,
            ),
        )

    @cached_property
    def with_raw_response(self) -> "AsyncReportsWithRawResponse":
        return AsyncReportsWithRawResponse(self)


class AsyncReportsWithRawResponse:
    """Raw `httpx2.Response` variants of the reports resource's public methods, bypassing
    model parsing. NOTE: `create_report` here returns only the initial `POST reports`
    response, not the follow-up `GET report` that the parsed `create_report()` performs."""

    def __init__(self, reports: AsyncReports) -> None:
        self._reports = reports

    async def create_report(self, data: models.CreateReportSpecification) -> httpx2.Response:
        return await self._reports._create_report_response(data)

    async def get_reports(
        self, *, query: typing.Optional[models.GetReportsQuery] = None
    ) -> httpx2.Response:
        return await self._reports._get_reports_response(query=query)

    async def get_report(self, report_id: str) -> httpx2.Response:
        return await self._reports._get_report_response(report_id)

    async def get_report_document(
        self,
        report_document_id: str,
        *,
        enable_content_encoding_url_header: typing.Optional[bool] = None,
    ) -> httpx2.Response:
        return await self._reports._get_report_document_response(
            report_document_id,
            enable_content_encoding_url_header=enable_content_encoding_url_header,
        )
