# Amazon Selling Partner API for Python

A client for the [Amazon Selling Partner API](https://developer-docs.amazon.com/sp-api)
generated from Amazon's API models by an [oagen](https://github.com/workos/oagen)
emitter (`codegen/`), the way the WorkOS tutorial
[How to build a custom SDK generator with oagen](https://workos.com/blog/build-a-custom-sdk-generator-with-oagen)
describes: the spec is the source of truth, `amzn_selling_partner/sdk/` is the
generated SDK (pydantic v2 models, one resource class per API version with a
sync and an async variant, the HTTP client with its retry and throttling
policy, the exceptions), committed to the repository so installing the package
pulls in no generator. Everything Amazon-specific that is not in the specs
(regions, Login-with-Amazon auth with Restricted Data Tokens, document helpers,
notification models) lives in `amzn_selling_partner.plugins.amazon_spapi`.

- **Bug reports:** https://github.com/dbritto-dev/amzn-selling-partner-python/issues
- **Migration from 0.1.x:** [MIGRATION.md](MIGRATION.md)
- **Updating the bundled specs:** [docs/UPDATING_SPECS.md](docs/UPDATING_SPECS.md)
- **Design notes:** [docs/PLAN.md](docs/PLAN.md)

## Installation

```sh
pip install amzn-selling-partner            # httpx2 + pydantic
pip install "amzn-selling-partner[aiohttp]"  # + aiohttp transport for the async client
```

Python 3.10 or later.

## Authentication

Create an application in Seller Central and authorize it for the seller; the
client needs the LWA client id, client secret and the seller's refresh token.
They can be passed explicitly or read from the environment
(`AMZN_SELLING_PARTNER_CLIENT_ID`, `AMZN_SELLING_PARTNER_CLIENT_SECRET`, `AMZN_SELLING_PARTNER_REFRESH_TOKEN`, or the old
`SELLING_PARTNER_APP_*` names).

```python
from amzn_selling_partner import SellingPartner

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
from amzn_selling_partner.plugins.amazon_spapi import with_rdt

orders = client.orders_v0.list_orders(
    marketplace_ids=["ATVPDKIKX0DER"],
    created_after="2024-01-01T00:00:00Z",
    request_options=with_rdt("buyerInfo", "shippingAddress"),
)
```

A custom token store (for example Redis) is any object with `get(key)` and
`set(key, token)`: `SellingPartner(token_store=MyStore())`.

## Region, marketplace and sandbox

```python
from amzn_selling_partner.plugins.amazon_spapi import Marketplace, Region

SellingPartner(region=Region.EU)                 # NA (default), EU, FE
SellingPartner(marketplace=Marketplace.DE)        # region derived from the marketplace
SellingPartner(region=Region.NA, sandbox=True)    # sandbox endpoint
```

`Marketplace` is a `StrEnum` of marketplace ids (`Marketplace.US == "ATVPDKIKX0DER"`)
with `.region` and `.country_code`.

## Calling operations

Every API version is a resource on the client (`client.orders_v0`,
`client.orders_v2026_01_01`); `client.orders` is the newest version. Methods
take keyword-only arguments named after the spec's parameters in snake_case;
request bodies are passed as `body=` (a model or a plain dict). Method names
are derived from the operation by oagen (`list_orders`, `get_order`,
`create_feed`); `amzn_selling_partner.sdk.resources.OPERATIONS` maps Amazon's
operationIds (`getOrders`) to them.

```python
from amzn_selling_partner import SellingPartner

client = SellingPartner()

order = client.orders_v0.get_order(order_id="123-1234567-1234567")
print(order.payload.order_status)

item = client.listings_items.get_listings_item(
    seller_id="A1SELLER", sku="MY-SKU", marketplace_ids=["ATVPDKIKX0DER"]
)

client.feeds.create_feed(body={"feedType": "POST_PRODUCT_DATA", "marketplaceIds": ["ATVPDKIKX0DER"], "inputFeedDocumentId": "..."})
```

Responses are frozen pydantic models generated from the spec
(`amzn_selling_partner.sdk.models.orders_v0.Order`); enums are `str` enums.
Errors raise `amzn_selling_partner.APIStatusError` subclasses
(`RateLimitExceededError`, `NotFoundError`, `AuthenticationError`, ...) with
`.status_code`, `.body` (the decoded error list), `.request_id` and `.response`.

### Async

```python
import asyncio
from amzn_selling_partner import AsyncSellingPartner

async def main() -> None:
    async with AsyncSellingPartner() as client:
        orders = client.orders_v0.iter_list_orders(marketplace_ids=["ATVPDKIKX0DER"], created_after="2024-01-01T00:00:00Z")
        async for order in orders:        # walks every page
            print(order.amazon_order_id)

asyncio.run(main())
```

The async client uses `httpx_aiohttp.AiohttpTransport` when the `aiohttp`
extra is installed (pass `prefer_aiohttp=False` to opt out).

### Pagination

Every paginated operation has an `iter_<method>` twin that yields the items
of every page, following the API's `nextToken` (and dropping the other
parameters on the next page where Amazon requires it):

```python
page = client.orders_v0.list_orders(marketplace_ids=["ATVPDKIKX0DER"], created_after="2024-01-01T00:00:00Z")
page.payload.orders          # this page
page.payload.next_token      # the NextToken, or None

for order in client.orders_v0.iter_list_orders(marketplace_ids=["ATVPDKIKX0DER"], created_after="2024-01-01T00:00:00Z"):
    ...                      # every order, fetching pages as needed
```

Every page fetch goes through the normal request path (auth, retries,
throttling).

### Raw mode

`RequestOptions(raw=True)` returns the decoded JSON (`dict`/`list`) without building models:

```python
from amzn_selling_partner import RequestOptions

data = client.orders_v0.get_order(order_id="...", request_options=RequestOptions(raw=True))
data["payload"]["OrderStatus"]
```

### Throttling and retries

Each operation has a token bucket seeded from the rate/burst table in the
Amazon documentation; 408, 429 and 5xx responses are retried with
`Retry-After` (or Amazon's `x-amzn-RateLimit-Limit` hint) or exponential
backoff. The policy is generated into `sdk/http_client.py` from
`sdkBehavior` in `codegen/oagen.config.ts`. Tune with
`SellingPartner(max_retries=..., throttle=False, timeout=httpx2.Timeout(...))`
or per call with `request_options=RequestOptions(timeout=5.0, max_retries=0)`;
`AMZN_SELLING_PARTNER_TIMEOUT` overrides the default timeout.

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

The emitter is not tied to Amazon: pointed at any OpenAPI 3 document it
produces the same kind of standalone SDK (models, resources, HTTP client,
errors). `tests/petstore_sdk` is generated from the petstore fixtures and
`tests/fixtures/tasks-api.yml` is the spec from the oagen tutorial:

```sh
cd codegen && npm ci --ignore-scripts
npm run sdk:generate -- --spec ../tests/fixtures/tasks-api.yml --namespace TasksClient --output ../tasks_sdk
```

`tasks_sdk/client.py` then has `TasksClient` / `AsyncTasksClient`; Swagger 2.0
files go through `npm run spec:build` first. See
[docs/UPDATING_SPECS.md](docs/UPDATING_SPECS.md) for the generator.

## Development

```sh
git clone --recurse-submodules https://github.com/dbritto-dev/amzn-selling-partner-python
uv sync --extra dev --extra aiohttp
uv run pytest
uv run pyright                            # strict, generated code included
uv run pytest benchmarks                  # pytest-benchmark: generated method vs hand-written httpx2 code
uv run python -m amzn_selling_partner.sandbox_tests   # every operation against its embedded examples

cd codegen && npm ci --ignore-scripts && npm run regenerate      # regenerate after a spec bump (Node 22)
cd codegen && npm test && npm run typecheck                      # the generator's own tests (vitest) and types
```

`src/amzn_selling_partner/sdk` and `tests/petstore_sdk` are generated; edit
the generator (`codegen/`) instead and commit the regenerated files (CI fails
on drift). See [docs/UPDATING_SPECS.md](docs/UPDATING_SPECS.md).
