# Amazon Selling Partner API for Python (`spapi`)

A spec-driven client for the [Amazon Selling Partner API](https://developer-docs.amazon.com/sp-api).
The bundled Swagger models are loaded at runtime and every operation becomes a
typed method on a sync client and an async client; there is no code-generation
step (optional `.pyi` stubs are provided for editors and type checkers).

The core (`spapi.spec`, `spapi.compile`, `spapi.runtime`) is API-agnostic: it
loads any OpenAPI 3.x or Swagger 2.0 document. Everything Amazon-specific lives
in `spapi.plugins.amazon_spapi`.

- **Bug reports:** https://github.com/dbritto-dev/amzn-selling-partner-python/issues
- **Migration from 0.1.x:** [MIGRATION.md](MIGRATION.md)
- **Updating the bundled specs:** [docs/UPDATING_SPECS.md](docs/UPDATING_SPECS.md)
- **Design notes:** [docs/PLAN.md](docs/PLAN.md)

## Installation

```sh
pip install amzn-selling-partner            # httpx2 + pydantic
pip install "amzn-selling-partner[aiohttp]"  # + aiohttp transport for the async client
```

Python 3.10 or later. The import name is `spapi`.

## Authentication

Create an application in Seller Central and authorize it for the seller; the
client needs the LWA client id, client secret and the seller's refresh token.
They can be passed explicitly or read from the environment
(`SPAPI_CLIENT_ID`, `SPAPI_CLIENT_SECRET`, `SPAPI_REFRESH_TOKEN`, or the old
`SELLING_PARTNER_APP_*` names).

```python
from spapi import SellingPartner

client = SellingPartner(
    client_id="amzn1.application-oa2-client....",
    client_secret="...",
    refresh_token="Atzr|...",
)
```

Access tokens are cached and refreshed once per process (single-flight);
grantless operations use the `client_credentials` grant with the right scope,
and operations that require a Restricted Data Token obtain one through the
Tokens API automatically. Operations that return PII only on request take an
explicit opt-in:

```python
from spapi.plugins.amazon_spapi import with_rdt

orders = client.orders.v0.get_orders(
    marketplace_ids=["ATVPDKIKX0DER"],
    created_after="2024-01-01T00:00:00Z",
    request_options=with_rdt("buyerInfo", "shippingAddress"),
)
```

A custom token store (for example Redis) is any object with `get(key)` and
`set(key, token)`: `SellingPartner(token_store=MyStore())`.

## Region, marketplace and sandbox

```python
from spapi.plugins.amazon_spapi import Marketplace, Region

SellingPartner(region=Region.EU)                 # NA (default), EU, FE
SellingPartner(marketplace=Marketplace.DE)        # region derived from the marketplace
SellingPartner(region=Region.NA, sandbox=True)    # sandbox endpoint
```

`Marketplace` is a `StrEnum` of marketplace ids (`Marketplace.US == "ATVPDKIKX0DER"`)
with `.region` and `.country_code`.

## Calling operations

APIs are attributes of the client, versions are attributes of the API, and
`latest` is an alias for the newest version. Methods take keyword-only
arguments named after the spec's parameters in snake_case; request bodies are
passed as `body=` (a model or a plain dict).

```python
from spapi import SellingPartner

client = SellingPartner()

order = client.orders.v0.get_order(order_id="123-1234567-1234567")
print(order.payload.order_status)

item = client.listings_items.latest.get_listings_item(
    seller_id="A1SELLER", sku="MY-SKU", marketplace_ids=["ATVPDKIKX0DER"]
)

client.feeds.latest.create_feed(body={"feedType": "POST_PRODUCT_DATA", "marketplaceIds": ["ATVPDKIKX0DER"], "inputFeedDocumentId": "..."})
```

Responses are frozen pydantic models generated from the spec (`client.orders.v0.models.Order`).
Errors raise `spapi.APIStatusError` subclasses (`RateLimitError`, `NotFoundError`, ...)
with `.status_code`, `.body` (the decoded error list), `.request_id` and `.response`.

### Async

```python
import asyncio
from spapi import AsyncSellingPartner

async def main() -> None:
    async with AsyncSellingPartner() as client:
        page = await client.orders.v0.get_orders(marketplace_ids=["ATVPDKIKX0DER"], created_after="2024-01-01T00:00:00Z")
        async for order in page:          # walks every page
            print(order.amazon_order_id)

asyncio.run(main())
```

The async client uses `httpx_aiohttp.AiohttpTransport` when the `aiohttp`
extra is installed (pass `prefer_aiohttp=False` to opt out).

### Pagination

Paginated operations return a `SyncPage` / `AsyncPage`:

```python
page = client.orders.v0.get_orders(marketplace_ids=["ATVPDKIKX0DER"], created_after="2024-01-01T00:00:00Z")
page.items          # this page's orders
page.next_token     # the NextToken, or None
page.next_page()    # the next SyncPage (None at the end)
for order in page:  # iterates over every page, fetching as needed
    ...
page.all()          # every item as a list
```

Every page fetch goes through the normal request path (auth, retries,
throttling). `paginate=None` disables page wrapping for one call; a
`paginate=Pagination(...)` argument overrides the detected descriptor.

### Raw mode

`raw=True` returns the decoded JSON (`dict`/`list`) without building models:

```python
data = client.orders.v0.get_order(order_id="...", raw=True)
data["payload"]["OrderStatus"]
```

### Throttling and retries

Each operation has a token bucket seeded from the rate/burst table in the
Amazon documentation; 429 and 5xx responses are retried with `Retry-After`
or exponential backoff. Tune with `SellingPartner(max_retries=..., throttle=False, timeout=httpx2.Timeout(...))`
or per call with `request_options=RequestOptions(timeout=5.0, max_retries=0)`.

### Documents and notifications

```python
content = client.documents.download_report("amzn1.tortuga.4...")              # bytes, gunzipped
client.documents.download_report("amzn1.tortuga.4...", path="report.tsv")     # streamed to disk
feed = client.documents.create_feed("POST_PRODUCT_DATA", ["ATVPDKIKX0DER"], xml, content_type="text/xml; charset=UTF-8")

message = client.notifications_models.parse(sqs_body)   # typed notification payload
```

### Injecting a custom HTTP client or transport

```python
import httpx2

client = SellingPartner(http_client=httpx2.Client(proxy="http://proxy:3128"))
client = SellingPartner(transport=httpx2.HTTPTransport(retries=1))
client = SellingPartner(transport=httpx2.MockTransport(handler))   # tests
```

Connection limits: `SellingPartner(limits=httpx2.Limits(max_connections=100, max_keepalive_connections=50))`.

## Using other APIs

```python
from spapi import Client

client = Client("path/to/specs/", base_url="https://api.example.com")
client.petstore.latest.list_pets(limit=10)
```

Plugins (`plugins=[...]`) supply API-specific knowledge through an
`annotate(document) -> document` hook; see `spapi.plugins`.

## Development

```sh
git clone --recurse-submodules https://github.com/dbritto-dev/amzn-selling-partner-python
uv sync --extra dev --extra aiohttp
uv run pytest
uv run pyright
uv run python -m spapi.stubgen --check     # stubs/ in sync with the specs
uv run python benchmarks/bench.py         # needs uvicorn (dev extra)
uv run python scripts/report_load_times.py
```

Type stubs live in `stubs/`; point your checker at them (`stubPath = "stubs"`
for pyright, `mypy_path = stubs` for mypy) to get typed `client.orders.v0.get_orders(...)`
signatures and models.
