# Migrating from 0.1.x

Version 0.2 replaces the hand-written `requests` client with an SDK generated
from Amazon's API models by [oagen](https://github.com/workos/oagen), inside
the same `amzn_selling_partner` package. The old `amzn_selling_partner` entry
points keep working as thin wrappers, but several things changed.

## Breaking changes

| Area | 0.1.x | 0.2 |
|---|---|---|
| Python | 3.10+ | 3.10+ (unchanged) |
| HTTP | `requests` | `httpx2` (sync and async), generated `sdk/_http.py` |
| Models | pydantic 1 (`.dict()`, `class Config`) | pydantic 2, generated from the specs (`.model_dump()`, frozen, `extra="allow"`), under `amzn_selling_partner.sdk.models.<api>_<version>` |
| Auth | LWA + AWS Signature V4 (boto3, `requests_aws4auth`) | **LWA only.** The `aws_*` constructor arguments are accepted and ignored with a `DeprecationWarning`; `ClientSessionAuth` / `ClientSessionAuthTemporaryCredentials` raise `NotImplementedError` |
| Exceptions | `requests.HTTPError` | `amzn_selling_partner.APIStatusError` and subclasses (`RateLimitExceededError`, `NotFoundError`, `AuthenticationError` (401), `AuthorizationError` (403), `ServerError`, ...), `APIConnectionError`, `APITimeoutError`, `APIResponseValidationError` |
| `http_session` attribute | `requests.Session` | removed; use `client.sp.http_client` (`httpx2.Client`) |
| Model field names | wire casing (`order.purchaseOrderNumber`) | snake_case attributes with wire aliases (`order.purchase_order_number`; `Order(purchaseOrderNumber=...)` still works thanks to `populate_by_name`) |
| Enum fields on models | Python enums (`PurchaseOrderState.NEW`) | generated `str` enums (`PurchaseOrderState.NEW == "New"`); the old enum classes still exist and compare equal |
| `reports.Client.get_reports` | slept `x-amzn-RateLimit-Limit * 100` seconds after every call | token-bucket throttling from the spec's rate table |
| Distribution deps | `requests`, `requests_aws4auth`, `boto3`, `pydantic<2` | `httpx2`, `pydantic>=2.9` |

## Kept entry points

| Old | Now |
|---|---|
| `amzn_selling_partner.client.SellingPartnerRegion` | alias of `amzn_selling_partner.plugins.amazon_spapi.Region` (same members and properties) |
| `amzn_selling_partner.client.BaseClient` | wraps `amzn_selling_partner.SellingPartner` (available as `.sp`) |
| `amzn_selling_partner.vendor.orders.Client` | `get_purchase_orders(query=)`, `get_purchase_order(id)` (+ `get_purchase_orders_status`, `submit_acknowledgement`) |
| `amzn_selling_partner.vendor.orders.Order`, `OrderDetails`, ... | spec-generated models (`amzn_selling_partner.sdk.models.vendor_orders_v1`) |
| `amzn_selling_partner.reports.Client` | all seven public methods, same signatures |
| `amzn_selling_partner.reports.Report`, `ReportDocument`, ... | spec-generated models |
| `*Query` / `CreateReport*Specification` / `ReportOptions` | kept (pydantic 2) |
| `amzn_selling_partner.utils.date`, `utils.file` | unchanged |

Environment variables `SELLING_PARTNER_APP_CLIENT_ID`, `..._CLIENT_SECRET`,
`..._REFRESH_TOKEN` are still honoured (`AMZN_SELLING_PARTNER_*` are the new names).

## New API

One resource per API version (`client.orders_v0`, `client.orders_v2026_01_01`;
`client.orders` is the newest version), one method per operation. Method names
are derived by oagen from the operation (`list_orders`, `get_order`,
`create_feed`); `amzn_selling_partner.sdk.resources.OPERATIONS` maps Amazon's
operationIds to them.

```python
from amzn_selling_partner import AsyncSellingPartner

async with AsyncSellingPartner(region=Region.NA) as client:
    async for order in client.vendor_orders_v1.iter_list_purchase_orders(created_after="2024-01-01T00:00:00Z"):
        ...                                # pages are followed automatically
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

def handler(request: httpx2.Request) -> httpx2.Response:
    if request.url.path.endswith("/auth/o2/token"):
        return httpx2.Response(200, json={"access_token": "t", "expires_in": 3600})
    return httpx2.Response(200, json={"payload": {"AmazonOrderId": "1", "PurchaseDate": "2024-01-01T00:00:00Z", "LastUpdateDate": "2024-01-01T00:00:00Z", "OrderStatus": "Shipped"}})

client = SellingPartner(transport=httpx2.MockTransport(handler), client_id="id", client_secret="s", refresh_token="r")
assert client.orders_v0.get_order(order_id="1").payload.order_status == "Shipped"
```

The same transport serves the LWA token endpoint, the Tokens API and
pre-signed document URLs, so a single handler can emulate a whole flow
(see `tests/_amazon_mock.py`). `amzn_selling_partner.sandbox_tests` runs every
operation through the examples embedded in Amazon's models the same way.

If your application still imports `httpx` elsewhere, `httpx2.alias_httpx()`
(called once at start-up, before anything imports `httpx`) makes both names
resolve to `httpx2`; the aiohttp transport then needs no bridging.
