# Amazon Selling Partner API for Python

A client for the [Amazon Selling Partner API](https://developer-docs.amazon.com/sp-api)
generated from Amazon's API models by an [oagen](https://github.com/workos/oagen)
emitter (`codegen/`), the way the WorkOS tutorial
[How to build a custom SDK generator with oagen](https://workos.com/blog/build-a-custom-sdk-generator-with-oagen)
describes: the spec is the source of truth, `amzn_selling_partner/sdk/` is the
generated SDK (pydantic v2 models, one resource class per API version, an
async client and a sync one with the same surface, the HTTP layer with its
retry and throttling policy, the exceptions), committed to the repository so
installing the package pulls in no generator. The examples below use the
async client, `AsyncSellingPartner`; `SellingPartner` is the synchronous
twin with identical resources and methods (see [Sync client](#sync-client)). Everything Amazon-specific that is not in the specs
(regions, Login-with-Amazon auth with Restricted Data Tokens, document helpers,
notification models) lives in `amzn_selling_partner.plugins.amazon_spapi`.

- **Bug reports:** https://github.com/dbritto-dev/amzn-selling-partner-python/issues
- **Migration from 0.1.x:** [MIGRATION.md](MIGRATION.md)
- **Updating the bundled specs:** [docs/UPDATING_SPECS.md](docs/UPDATING_SPECS.md)
- **Design notes:** [docs/PLAN.md](docs/PLAN.md)

## Installation

```sh
pip install amzn-selling-partner
pip install "amzn-selling-partner[aiohttp]"
```

The package depends on `httpx2` and `pydantic` only; the `aiohttp` extra adds
the aiohttp transport the async client prefers when it is installed.
Python 3.10 or later.

## Authentication

Create an application in Seller Central and authorize it for the seller; the
client needs the LWA client id, client secret and the seller's refresh token.
They can be passed explicitly or read from the environment
(`AMZN_SELLING_PARTNER_CLIENT_ID`, `AMZN_SELLING_PARTNER_CLIENT_SECRET`, `AMZN_SELLING_PARTNER_REFRESH_TOKEN`, or the old
`SELLING_PARTNER_APP_*` names).

```python
from amzn_selling_partner import AsyncSellingPartner

client = AsyncSellingPartner(
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
from amzn_selling_partner import Marketplace
from amzn_selling_partner.plugins.amazon_spapi import with_rdt

orders = await client.orders_v0.list_orders(
    marketplace_ids=[Marketplace.US],
    created_after="2024-01-01T00:00:00Z",
    request_options=with_rdt("buyerInfo", "shippingAddress"),
)
```

A custom token store (for example Redis) is any object with `get(key)` and
`set(key, token)`: `AsyncSellingPartner(token_store=MyStore())`.

## Region, marketplace and sandbox

```python
from amzn_selling_partner import AsyncSellingPartner, Marketplace, Region

AsyncSellingPartner(region=Region.EU)
AsyncSellingPartner(marketplace=Marketplace.DE)
AsyncSellingPartner(region=Region.NA, sandbox=True)
```

`Region` is `NA` (the default), `EU` or `FE`; a `marketplace` implies its
region; `sandbox=True` selects the sandbox endpoint of the region.

`Marketplace` is a `str` enum of marketplace ids (`Marketplace.US == "ATVPDKIKX0DER"`)
with `.region` and `.country_code`; pass its members wherever an operation
takes marketplace ids (`marketplace_ids=[Marketplace.US, Marketplace.CA]`).

## Calling operations

Every API version is a resource on the client (`client.orders_v0`,
`client.orders_v2026_01_01`); `client.orders` is the newest version. Every
method is a coroutine named after the operation as oagen derives it
(`list_orders`, `get_order`, `create_feed`); path parameters, the request body
and required parameters are positional (keywords work too), optional
parameters are keyword-only, all named after the spec's parameters in
snake_case; request bodies are a model from `amzn_selling_partner.sdk.models`
(a plain dict with the wire names is accepted too). Every enumerated value in
the specs is a `str` enum in the same package (`OrderOrderStatus.SHIPPED`,
`FeedProcessingStatus.DONE`), usable as arguments and returned in responses;
`Marketplace` covers the marketplace ids. `amzn_selling_partner.sdk.resources.OPERATIONS`
maps Amazon's operationIds (`getOrders`) to the method names.

```python
import asyncio
from amzn_selling_partner import AsyncSellingPartner, Marketplace
from amzn_selling_partner.sdk.models.feeds_v2021_06_30 import CreateFeedSpecification
from amzn_selling_partner.sdk.models.orders_v0 import OrderOrderStatus


async def main() -> None:
    async with AsyncSellingPartner() as client:
        order = await client.orders_v0.get_order("123-1234567-1234567")
        if order.payload.order_status is OrderOrderStatus.SHIPPED:
            print("shipped")

        item = await client.listings_items.get_listings_item(
            seller_id="A1SELLER", sku="MY-SKU", marketplace_ids=[Marketplace.US]
        )

        await client.feeds.create_feed(
            CreateFeedSpecification(
                feed_type="POST_PRODUCT_DATA",
                marketplace_ids=[Marketplace.US],
                input_feed_document_id="...",
            )
        )


asyncio.run(main())
```

The async client uses `httpx_aiohttp.AiohttpTransport` when the `aiohttp`
extra is installed (pass `prefer_aiohttp=False` to opt out); `async with`
closes the connection pool, `await client.aclose()` does the same by hand.

Responses are frozen pydantic models generated from the spec
(`amzn_selling_partner.sdk.models.orders_v0.Order`); enums are `str` enums.
Errors raise `amzn_selling_partner.APIStatusError` subclasses
(`RateLimitExceededError`, `NotFoundError`, `AuthenticationError`, ...) with
`.status_code`, `.body` (the decoded error list), `.request_id` and `.response`.

### Sync client

`SellingPartner` is the synchronous client: the same resources, method names,
arguments, models and errors, without `await`; `iter_<method>` returns a plain
iterator and `with` / `close()` release the pool. Both are generated from the
same plan per operation, so they never drift apart.

```python
from amzn_selling_partner import Marketplace, SellingPartner

with SellingPartner() as client:
    order = client.orders_v0.get_order("123-1234567-1234567")
    for order in client.orders_v0.iter_list_orders(marketplace_ids=[Marketplace.US]):
        ...
```

Every option below applies to both clients.

### Pagination

Every paginated operation has an `iter_<method>` twin that yields the items
of every page, following the API's `nextToken` (and dropping the other
parameters on the next page where Amazon requires it):

```python
from amzn_selling_partner import Marketplace
from amzn_selling_partner.sdk.models.orders_v0 import OrderOrderStatus

page = await client.orders_v0.list_orders(
    marketplace_ids=[Marketplace.US], created_after="2024-01-01T00:00:00Z", order_statuses=[OrderOrderStatus.UNSHIPPED]
)
page.payload.orders
page.payload.next_token

async for order in client.orders_v0.iter_list_orders(
    marketplace_ids=[Marketplace.US], created_after="2024-01-01T00:00:00Z", order_statuses=[OrderOrderStatus.UNSHIPPED]
):
    ...
```

Every page fetch goes through the normal request path (auth, retries,
throttling).

### Raw mode

`RequestOptions(raw=True)` returns the decoded JSON (`dict`/`list`) without building models:

```python
from amzn_selling_partner import RequestOptions

data = await client.orders_v0.get_order("...", request_options=RequestOptions(raw=True))
data["payload"]["OrderStatus"]
```

### Throttling and retries

Each operation has a token bucket seeded from the rate/burst table in the
Amazon documentation; 408, 429 and 5xx responses are retried with
`Retry-After` (or Amazon's `x-amzn-RateLimit-Limit` hint) or exponential
backoff. The policy is generated into `sdk/_http.py` from
`sdkBehavior` in `codegen/oagen.config.ts`. Tune with
`AsyncSellingPartner(max_retries=..., throttle=False, timeout=httpx2.Timeout(...))`
or per call with `request_options=RequestOptions(timeout=5.0, max_retries=0)`;
`client.with_options(max_retries=0)` derives a client with some options changed
that shares the connection pool; `AMZN_SELLING_PARTNER_TIMEOUT` overrides the
default timeout.

### Documents and notifications

```python
content = await client.documents.download_report("amzn1.tortuga.4...")
await client.documents.download_report("amzn1.tortuga.4...", path="report.tsv")
feed = await client.documents.create_feed("POST_PRODUCT_DATA", [Marketplace.US], xml, content_type="text/xml; charset=UTF-8")

message = client.notifications_models.parse(sqs_body)
```

`download_report` returns the decompressed bytes, or streams to `path` when
given; `create_feed` uploads the document and creates the feed in one call;
`parse` turns an SQS message body into the typed notification model without
any I/O.

### Injecting a custom HTTP client or transport

```python
import httpx2

client = AsyncSellingPartner(http_client=httpx2.AsyncClient(proxy="http://proxy:3128"))
client = AsyncSellingPartner(transport=httpx2.AsyncHTTPTransport(retries=1))
client = AsyncSellingPartner(transport=httpx2.MockTransport(handler))
client = SellingPartner(http_client=httpx2.Client(proxy="http://proxy:3128"))
```

The sync client takes the `httpx2.Client` counterparts; a `MockTransport` is
how the tests run without a network.

Connection limits: `AsyncSellingPartner(limits=httpx2.Limits(max_connections=100, max_keepalive_connections=50))`.

## Using other APIs

The emitter is not tied to Amazon: pointed at any OpenAPI 3 document it
produces the same kind of standalone SDK (models, resources, HTTP client,
errors). `tests/petstore_sdk` is generated from the petstore fixtures and
`tests/fixtures/tasks-api.yml` is the spec from the oagen tutorial:

```sh
cd codegen && npm ci --ignore-scripts
npm run sdk:generate -- --spec ../tests/fixtures/tasks-api.yml --namespace TasksClient --output ../tasks_sdk
```

`tasks_sdk/client.py` then has `AsyncTasksClient` / `TasksClient`. Amazon's
Swagger 2.0 files go through `npm run spec:build` first, which writes the one
OpenAPI 3 document the generator runs against, `codegen/spec/open-api-spec.yaml`
(committed, like `spec/open-api-spec.yaml` in
[workos/openapi-spec](https://github.com/workos/openapi-spec)). See
[docs/UPDATING_SPECS.md](docs/UPDATING_SPECS.md) for the generator.

## Development

```sh
git clone --recurse-submodules https://github.com/dbritto-dev/amzn-selling-partner-python
uv sync --extra dev --extra aiohttp
uv run pytest
uv run pyright
uv run pytest benchmarks
uvx nox -s security_test
uv run python -m amzn_selling_partner.sandbox_tests

cd codegen && npm ci --ignore-scripts && npm run regenerate
cd codegen && npm test && npm run typecheck
```

pyright runs strict over the generated code too; the benchmarks assert the
generated method stays within 10 % of hand-written `httpx2` code; the security
session runs bandit and safety as in CI; the sandbox runner sends every
operation its embedded examples. The last two lines regenerate the SDK after a
spec bump (Node 24) and run the generator's own vitest suite and type check.

`codegen/spec/*.yaml`, `src/amzn_selling_partner/sdk` and `tests/petstore_sdk`
are generated; edit the generator (`codegen/src/python`), the policy
(`codegen/src/policy`) or the spec build (`codegen/src/spec`) instead and commit
the regenerated files (CI fails on drift). See
[docs/UPDATING_SPECS.md](docs/UPDATING_SPECS.md).
