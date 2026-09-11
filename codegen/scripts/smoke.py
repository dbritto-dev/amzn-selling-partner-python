"""Prove the generated Amazon SDK runs end to end, without a network.

Instantiates the client over ``httpx2.MockTransport``, calls one list operation
with an enum query parameter, one create with a body model and one 404, and
prints the parsed results and the exact requests that went out. Run with
``npm run smoke`` (or ``uv run python codegen/scripts/smoke.py`` from the repo root).
"""

from __future__ import annotations

import json
import pathlib
import sys

import httpx2

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from amzn_selling_partner.sdk import Client, NotFoundError, RequestOptions  # noqa: E402
from amzn_selling_partner.sdk.models.feeds_v2021_06_30 import CreateFeedSpecification  # noqa: E402
from amzn_selling_partner.sdk.models.reports_v2021_06_30 import ReportsV20210630ProcessingStatuses as ProcessingStatus  # noqa: E402

seen: list[tuple[str, str, str | None]] = []


def handler(request: httpx2.Request) -> httpx2.Response:
    seen.append((request.method, str(request.url), request.content.decode() or None))
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


client = Client(base_url="https://sellingpartnerapi-na.amazon.com", transport=httpx2.MockTransport(handler), throttle=False)

page = client.reports.list_reports(
    report_types=["GET_MERCHANT_LISTINGS_ALL_DATA"], processing_statuses=[ProcessingStatus.DONE], page_size=10
)
print("reports:", [(r.report_id, r.processing_status) for r in page.reports])

created = client.feeds.create_feed(
    CreateFeedSpecification(feed_type="POST_PRODUCT_DATA", marketplace_ids=["ATVPDKIKX0DER"], input_feed_document_id="doc-1")
)
print("created feed:", created.feed_id)

raw = client.reports.list_reports(processing_statuses=[ProcessingStatus.DONE], request_options=RequestOptions(raw=True))
print("raw:", json.dumps(raw)[:60])

try:
    client.orders.get_order("111-0000000-0000000")
except NotFoundError as exc:
    print("404:", exc, "| body:", exc.body)

print("requests:")
print(*seen, sep="\n")

query = seen[0][1]
assert "processingStatuses=DONE" in query, query  # the enum's value, not "ProcessingStatuses.DONE"
assert "reportTypes=GET_MERCHANT_LISTINGS_ALL_DATA" in query and "pageSize=10" in query, query
assert seen[1][2] == '{"feedType":"POST_PRODUCT_DATA","marketplaceIds":["ATVPDKIKX0DER"],"inputFeedDocumentId":"doc-1"}', seen[1][2]
print("ok")
