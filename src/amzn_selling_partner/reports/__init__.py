"""Compatibility ``reports`` resource over ``spapi`` (Reports API 2021-06-30)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict

from .. import client as _client
from .._compat import query_kwargs, require_str, to_body
from ..utils import file as _file
from .models import (
    CompressionAlgorithm,
    DistributorView,
    MarketPlaceId,
    ProcessingStatus,
    ReportPeriod,
    ReportType,
    SchedulePeriod,
    SellingProgram,
)


class ReportOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reportPeriod: ReportPeriod | str | None = None
    distributorView: DistributorView | str | None = None
    sellingProgram: SellingProgram | str | None = None


class CreateReportSpecification(BaseModel):
    model_config = ConfigDict(extra="allow")

    reportType: ReportType | str
    marketplaceIds: list[MarketPlaceId | str]
    reportOptions: ReportOptions | dict[str, str] | None = None
    dataStartTime: str | None = None
    dataEndTime: str | None = None


class CreateReportScheduleSpecification(BaseModel):
    model_config = ConfigDict(extra="allow")

    reportType: ReportType | str
    marketplaceIds: list[MarketPlaceId | str]
    period: SchedulePeriod | str
    reportOptions: ReportOptions | dict[str, str] | None = None
    nextReportCreationTime: str | None = None


class GetReportsQuery(BaseModel):
    model_config = ConfigDict(extra="allow")

    reportTypes: list[ReportType | str] | None = None
    processingStatuses: list[ProcessingStatus | str] | None = None
    marketplaceIds: list[MarketPlaceId | str] | None = None
    pageSize: int | None = None
    createdSince: str | None = None
    createdUntil: str | None = None
    nextToken: str | None = None


class Client(_client.BaseClient):
    def get_resource_path(self) -> str:
        return "reports/2021-06-30"

    @property
    def api(self) -> Any:
        return self.sp.reports.v2021_06_30

    def create_report(self, data: CreateReportSpecification | dict[str, Any]) -> Any:
        """Create the report and return the ``Report`` (as before: one extra ``getReport`` call)."""
        response = self.api.create_report(body=to_body(data))
        return self.get_report(response.report_id)

    def get_reports(self, *, query: GetReportsQuery | dict[str, Any] | None = None, pages_limit: int = 3) -> list[Any]:
        """Reports across up to ``pages_limit`` pages."""
        reports: list[Any] = []
        page = self.api.get_reports(**query_kwargs(query))
        for i, p in enumerate(page.pages()):
            reports.extend(p.items)
            if i + 1 >= pages_limit:
                break
        return reports

    def get_report(self, report_id: str) -> Any:
        require_str(report_id, "report_id")
        return self.api.get_report(report_id=report_id)

    def get_report_document(self, report_document_id: str, *, enable_content_encoding_url_header: bool | None = None) -> Any:
        self._check_id(report_document_id)
        kwargs: dict[str, Any] = {"report_document_id": report_document_id}
        if enable_content_encoding_url_header is not None:
            kwargs["enable_content_encoding_url_header"] = enable_content_encoding_url_header
        return self.api.get_report_document(**kwargs)

    def get_report_document_content(self, report_document_id: str, *, enable_content_encoding_url_header: bool | None = None) -> Any:
        """The document parsed as JSON (report types with JSON payloads)."""
        return json.loads(self._raw_content(report_document_id, enable_content_encoding_url_header))

    def download_report_document_content(
        self, report_document_id: str, file_path: str, *, enable_content_encoding_url_header: bool | None = None
    ) -> None:
        self._check_id(report_document_id)
        require_str(file_path, "file_path")
        _file.write_binary_file(file_path, self._raw_content(report_document_id, enable_content_encoding_url_header))

    def _raw_content(self, report_document_id: str, enable_content_encoding_url_header: bool | None) -> bytes:
        from spapi.plugins._amazon.documents import download_document

        doc = self.get_report_document(report_document_id, enable_content_encoding_url_header=enable_content_encoding_url_header)
        return download_document(doc.url, compression=doc.compression_algorithm, http_client=self.sp.http_client)

    @staticmethod
    def _check_id(report_document_id: str) -> None:
        require_str(report_document_id, "report_document_id")


def __getattr__(name: str) -> Any:
    """Spec-generated models (``Report``, ``ReportDocument``, ``ReportSchedule``, ...)."""
    from .models import model

    return model(name)


__all__ = [
    "Client",
    "CompressionAlgorithm",
    "CreateReportScheduleSpecification",
    "CreateReportSpecification",
    "DistributorView",
    "GetReportsQuery",
    "MarketPlaceId",
    "ProcessingStatus",
    "ReportOptions",
    "ReportPeriod",
    "ReportType",
    "SchedulePeriod",
    "SellingProgram",
]
