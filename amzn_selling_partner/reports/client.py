import copy
import gzip
import json
import time
import typing

from .. import client, utils
from . import models


class Client(client.BaseClient):
    def get_resource_path(self) -> str:
        return "reports/2021-06-30"

    def _create_report_response(
        self, data: models.CreateReportSpecification
    ) -> models.CreateReportResponse:
        _response = self.http_session.post(
            self.get_operation_endpoint("reports"),
            json=data.dict(exclude_none=True),
        )
        _response.raise_for_status()
        return models.CreateReportResponse(**_response.json())

    def create_report(self, data: models.CreateReportSpecification) -> models.Report:
        return self.get_report(self._create_report_response(data).reportId)

    def _get_reports_response(
        self,
        *,
        query: typing.Optional[models.GetReportsQuery] = None,
    ):
        _response = self.http_session.get(
            self.get_operation_endpoint("reports"),
            params=query and query.dict(exclude_none=True),
        )
        _time_to_wait = float(_response.headers.get("x-amzn-RateLimit-Limit", 0.03)) * 100
        time.sleep(_time_to_wait)
        _response.raise_for_status()
        return models.GetReportsResponse(**_response.json())

    def get_reports(
        self, *, query: typing.Optional[models.GetReportsQuery] = None, pages_limit: int = 3
    ):
        data = self._get_reports_response(
            query=query,
        )

        next_token = data.nextToken

        if next_token is None or pages_limit < 2:  # noqa
            return data.reports

        _query = models.GetReportsQuery()
        _query.nextToken = next_token

        return data.reports + self.get_reports(query=_query, pages_limit=pages_limit - 1)

    def _get_report_response(self, report_id: str) -> models.Report:
        _response = self.http_session.get(self.get_operation_endpoint(f"reports/{report_id}"))
        _response.raise_for_status()
        return models.Report(**_response.json())

    def get_report(self, report_id: str) -> models.Report:
        if not report_id or not isinstance(report_id, str):
            raise ValueError(f"report_id must be a string present but found `{report_id}`")

        return self._get_report_response(report_id)

    def _get_report_document_response(
        self,
        report_document_id: str,
        *,
        enable_content_encoding_url_header: typing.Optional[bool] = None,
    ) -> models.ReportDocument:
        _response = self.http_session.get(
            self.get_operation_endpoint(f"documents/{report_document_id}"),
            params=(
                {
                    "enableContentEncodingUrlHeader": str(
                        enable_content_encoding_url_header
                    ).lower(),
                }
                if enable_content_encoding_url_header is not None
                else None
            ),
        )
        _response.raise_for_status()
        return models.ReportDocument(**_response.json())

    def get_report_document(
        self,
        report_document_id: str,
        *,
        enable_content_encoding_url_header: typing.Optional[bool] = None,
    ) -> models.ReportDocument:
        if not report_document_id or not isinstance(report_document_id, str):
            raise ValueError(
                f"report_document_id must be a string present but found `{report_document_id}`"
            )

        return self._get_report_document_response(
            report_document_id,
            enable_content_encoding_url_header=enable_content_encoding_url_header,
        )

    def _get_report_document_raw_content(
        self,
        report_document_id: str,
        *,
        enable_content_encoding_url_header: typing.Optional[bool] = None,
    ) -> bytes:
        _report_document = self.get_report_document(
            report_document_id,
            enable_content_encoding_url_header=enable_content_encoding_url_header,
        )
        _download_session = copy.copy(self.http_session)
        _download_session.auth = None
        _download_response = _download_session.get(_report_document.url)
        _download_response.raise_for_status()
        if (
            _report_document.compressionAlgorithm == models.CompressionAlgorithm.GZIP
            and _download_response.headers.get("Content-Encoding", "").lower() != "gzip"
        ):
            return gzip.decompress(_download_response.content)
        return _download_response.content

    def _get_report_document_content(
        self,
        report_document_id: str,
        *,
        enable_content_encoding_url_header: typing.Optional[bool] = None,
    ) -> typing.Dict:
        _report_document_raw_content = self._get_report_document_raw_content(
            report_document_id,
            enable_content_encoding_url_header=enable_content_encoding_url_header,
        )
        return json.loads(_report_document_raw_content)

    def get_report_document_content(
        self,
        report_document_id: str,
        *,
        enable_content_encoding_url_header: typing.Optional[bool] = None,
    ) -> typing.Dict:
        if not report_document_id or not isinstance(report_document_id, str):
            raise ValueError(
                f"report_document_id must be a string present but found `{report_document_id}`"
            )

        return self._get_report_document_content(
            report_document_id,
            enable_content_encoding_url_header=enable_content_encoding_url_header,
        )

    def download_report_document_content(
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
            self._get_report_document_raw_content(
                report_document_id,
                enable_content_encoding_url_header=enable_content_encoding_url_header,
            ),
        )
