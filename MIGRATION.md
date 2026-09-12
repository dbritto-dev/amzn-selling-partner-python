# Migrating from 0.1.x to 1.0

Version 1.0 replaces the hand-written `requests` client with an SDK generated
from Amazon's API models by [oagen](https://github.com/workos/oagen), inside
the same `amzn_selling_partner` package. The 0.1.x entry points (`client`,
`reports`, `vendor`, `utils`) are gone; this page maps them to the new API.

## What changed

| Area | 0.1.x | 1.0 |
|---|---|---|
| Python | 3.10+ | 3.10+ |
| HTTP | `requests` | `httpx2`, sync and async, in the generated `sdk/_http.py` |
| Models | pydantic 1 (`.dict()`, `class Config`) | pydantic 2, generated from the specs (`.model_dump()`, frozen, `extra="allow"`), under `amzn_selling_partner.sdk.models.<api>_<version>` |
| Auth | LWA + AWS Signature V4 (boto3, `requests_aws4auth`) | LWA only; Restricted Data Tokens and grantless scopes are obtained automatically |
| Errors | `requests.HTTPError` | `amzn_selling_partner.APIStatusError` and subclasses (`RateLimitExceededError`, `NotFoundError`, `AuthenticationError` for 401, `AuthorizationError` for 403, `ServerError`, ...), `APIConnectionError`, `APITimeoutError`, `APIResponseValidationError` |
| Model fields | wire casing (`order.purchaseOrderNumber`) | snake_case attributes with wire aliases (`order.purchase_order_number`; `Order(purchaseOrderNumber=...)` still validates) |
| Enums | hand-written Python enums | generated `str` enums (`PurchaseOrderState.NEW == "New"`) |
| Rate limits | `reports.Client.get_reports` slept `x-amzn-RateLimit-Limit * 100` seconds after every call | token-bucket throttling from the spec's rate table, retries with `Retry-After` |
| Dependencies | `requests`, `requests_aws4auth`, `boto3`, `pydantic<2` | `httpx2`, `pydantic>=2.9` |

## Entry points

| 0.1.x | 1.0 |
|---|---|
| `amzn_selling_partner.client.BaseClient(selling_partner_region=..., selling_partner_app_client_id=..., ...)` | `amzn_selling_partner.AsyncSellingPartner(region=..., client_id=..., client_secret=..., refresh_token=...)` or the synchronous `SellingPartner`; one client serves every API |
| `amzn_selling_partner.client.SellingPartnerRegion.NORTH_AMERICA` / `EUROPE` / `FAR_EAST` | `amzn_selling_partner.Region.NA` / `EU` / `FE` |
| `aws_access_key_id`, `aws_secret_access_key`, `aws_selling_partner_role`, `aws_selling_partner_role_session_name` | removed; the Selling Partner API no longer uses AWS Signature V4 |
| `amzn_selling_partner.client.auth.ClientSessionAuthAccessToken` | `amzn_selling_partner.plugins.amazon_spapi.LWAAuth` (created by the client; pass `token_store=` for a custom cache) |
| `amzn_selling_partner.client.auth.ClientSessionAuth`, `ClientSessionAuthTemporaryCredentials` | removed |
| `amzn_selling_partner.vendor.orders.Client().get_purchase_orders(query=...)` | `client.vendor_orders_v1.list_purchase_orders(created_after=..., ...)` (`iter_list_purchase_orders` follows the pages) |
| `amzn_selling_partner.vendor.orders.Client().get_purchase_order(id)` | `client.vendor_orders_v1.get_purchase_order(id)` |
| `amzn_selling_partner.vendor.orders.Order`, `OrderDetails`, ... | `amzn_selling_partner.sdk.models.vendor_orders_v1` |
| `amzn_selling_partner.reports.Client().get_reports(query=...)` | `client.reports.list_reports(report_types=[...], ...)` (`iter_list_reports` follows the pages) |
| `amzn_selling_partner.reports.Client().create_report(...)` | `client.reports.create_report(CreateReportSpecification(...))` |
| `amzn_selling_partner.reports.Client().get_report(id)` | `client.reports.get_report(id)` |
| `amzn_selling_partner.reports.Client().get_report_document(id)` / download | `client.reports.get_document(id)`; `client.documents.download_report(id)` downloads and decompresses it |
| `amzn_selling_partner.reports.Report`, `ReportDocument`, `*Query`, `CreateReport*Specification`, `ReportOptions` | `amzn_selling_partner.sdk.models.reports_v2021_06_30` |
| `amzn_selling_partner.utils.date.amazon_isoformat(value)` | pass a `datetime` directly; the client serialises it as ISO 8601 with `Z` |
| `amzn_selling_partner.utils.date.datetime_utcnow()` / `datetime_utcpast(...)` | `datetime.datetime.now(datetime.timezone.utc)` and `datetime.timedelta` |
| `amzn_selling_partner.utils.file.write_binary_file(path, content)` | `client.documents.download_report(id, path=...)` streams to a file; otherwise `pathlib.Path(path).write_bytes(content)` |
| `SELLING_PARTNER_APP_CLIENT_ID`, `..._CLIENT_SECRET`, `..._REFRESH_TOKEN` | still read; `AMZN_SELLING_PARTNER_CLIENT_ID`, `..._CLIENT_SECRET`, `..._REFRESH_TOKEN` are the new names |

`amzn_selling_partner.sdk.resources.OPERATIONS` maps Amazon's operationIds
(`getPurchaseOrders`) to the generated method names.

## The 1.0 API in short

One resource per API version (`client.orders_v0`, `client.orders_v2026_01_01`;
`client.orders` is the newest version), one method per operation, every
paginated operation with an `iter_<method>` twin.

```python
from amzn_selling_partner import AsyncSellingPartner, Region

async with AsyncSellingPartner(region=Region.NA) as client:
    async for order in client.vendor_orders_v1.iter_list_purchase_orders(created_after="2024-01-01T00:00:00Z"):
        ...
    report = await client.reports.get_report("...")
    content = await client.documents.download_report(report.report_document_id)
```

`SellingPartner` is the synchronous client with the same surface (no `await`,
plain iterators). See the README for auth, pagination and raw mode.

## Testing: `respx` and `pytest-httpx` do not support `httpx2`

Both libraries patch `httpx`, not `httpx2`. Use `httpx2.MockTransport` and
inject it:

```python
import httpx2
from amzn_selling_partner import SellingPartner
from amzn_selling_partner.sdk.models.orders_v0 import OrderOrderStatus

def handler(request: httpx2.Request) -> httpx2.Response:
    if request.url.path.endswith("/auth/o2/token"):
        return httpx2.Response(200, json={"access_token": "t", "expires_in": 3600})
    return httpx2.Response(200, json={"payload": {"AmazonOrderId": "1", "PurchaseDate": "2024-01-01T00:00:00Z", "LastUpdateDate": "2024-01-01T00:00:00Z", "OrderStatus": "Shipped"}})

client = SellingPartner(transport=httpx2.MockTransport(handler), client_id="id", client_secret="s", refresh_token="r")
assert client.orders_v0.get_order("1").payload.order_status is OrderOrderStatus.SHIPPED
```

The same transport serves the LWA token endpoint, the Tokens API and
pre-signed document URLs, so a single handler can emulate a whole flow
(see `tests/_amazon_mock.py`). `tests/sandbox.py` runs every operation through
the examples embedded in Amazon's models the same way.

If your application still imports `httpx` elsewhere, `httpx2.alias_httpx()`
(called once at start-up, before anything imports `httpx`) makes both names
resolve to `httpx2`; the aiohttp transport then needs no bridging.
