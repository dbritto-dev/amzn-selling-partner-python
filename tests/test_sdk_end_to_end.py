"""The generated Amazon SDK end to end over ``httpx2.MockTransport``: a list with an
enum query parameter, a create with a body model, a 404, and what went out on the wire."""

from __future__ import annotations

import asyncio

import httpx2
import pytest

from amzn_selling_partner.sdk import AsyncClient, Client, NotFoundError, RequestOptions
from amzn_selling_partner.sdk.models.feeds_v2021_06_30 import CreateFeedSpecification
from amzn_selling_partner.sdk.models.reports_v2021_06_30 import ReportsV20210630ProcessingStatuses as ProcessingStatus

BASE = "https://sellingpartnerapi-na.amazon.com"


def _handler(seen: list[tuple[str, str, bytes]]):
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append((request.method, str(request.url), request.content))
        path = request.url.path
        if path == "/reports/2021-06-30/reports":
            return httpx2.Response(
                200,
                json={
                    "reports": [
                        {
                            "reportId": "r-1",
                            "reportType": "GET_MERCHANT_LISTINGS_ALL_DATA",
                            "processingStatus": "DONE",
                            "createdTime": "2024-01-01T00:00:00Z",
                        }
                    ]
                },
            )
        if path == "/feeds/2021-06-30/feeds":
            return httpx2.Response(202, json={"feedId": "f-1"})
        return httpx2.Response(404, json={"errors": [{"code": "NotFound", "message": path}]}, headers={"x-amzn-RequestId": "req-404"})

    return handler


def test_sync_client_end_to_end() -> None:
    seen: list[tuple[str, str, bytes]] = []
    client = Client(base_url=BASE, transport=httpx2.MockTransport(_handler(seen)), throttle=False)

    page = client.reports.list_reports(
        report_types=["GET_MERCHANT_LISTINGS_ALL_DATA"], processing_statuses=[ProcessingStatus.DONE], page_size=10
    )
    assert [(r.report_id, r.processing_status) for r in page.reports] == [("r-1", "DONE")]
    # the enum's value reaches the wire, not "ProcessingStatuses.DONE"
    assert (
        seen[-1][1] == f"{BASE}/reports/2021-06-30/reports?reportTypes=GET_MERCHANT_LISTINGS_ALL_DATA&processingStatuses=DONE&pageSize=10"
    )

    created = client.feeds.create_feed(
        CreateFeedSpecification(feed_type="POST_PRODUCT_DATA", marketplace_ids=["ATVPDKIKX0DER"], input_feed_document_id="doc-1")
    )
    assert created.feed_id == "f-1"
    assert seen[-1][2] == b'{"feedType":"POST_PRODUCT_DATA","marketplaceIds":["ATVPDKIKX0DER"],"inputFeedDocumentId":"doc-1"}'

    raw = client.reports.list_reports(processing_statuses=[ProcessingStatus.DONE], request_options=RequestOptions(raw=True))
    assert raw["reports"][0]["reportId"] == "r-1"

    with pytest.raises(NotFoundError) as info:
        client.orders_v0.get_order("111-0000000-0000000")
    assert info.value.request_id == "req-404" and info.value.body.errors[0].code == "NotFound"


def test_async_client_end_to_end() -> None:
    seen: list[tuple[str, str, bytes]] = []

    async def run() -> None:
        async with AsyncClient(base_url=BASE, transport=httpx2.MockTransport(_handler(seen)), throttle=False) as client:
            page = await client.reports.list_reports(processing_statuses=[ProcessingStatus.DONE])
            assert page.reports[0].report_id == "r-1" and "processingStatuses=DONE" in seen[-1][1]
            created = await client.feeds.create_feed(
                CreateFeedSpecification(feed_type="POST_PRODUCT_DATA", marketplace_ids=["ATVPDKIKX0DER"], input_feed_document_id="doc-1")
            )
            assert created.feed_id == "f-1"
            with pytest.raises(NotFoundError):
                await client.orders_v0.get_order("111-0000000-0000000")

    asyncio.run(run())
