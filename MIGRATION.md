# Migration guide: requests → httpx2

This release replaces `requests` with [`httpx2`](https://httpx2.pydantic.dev/) (Pydantic
Services' actively maintained continuation of `httpx`) and restructures the SDK around a
first-class `Client` (sync) and `AsyncClient` (async), following the shape used by the
Anthropic and OpenAI Python SDKs. Most existing code keeps working unmodified; this document
lists every breaking and behavior change.

## New: unified `Client` / `AsyncClient`

```python
import amzn_selling_partner as sp

client = sp.Client()  # or sp.AsyncClient()
client.reports.create_report(...)
client.vendor.orders.get_purchase_orders(...)
```

Both accept the same constructor kwargs as before (`selling_partner_region`, all SP-API/AWS
credential kwargs, `sandbox`), plus new options: `timeout` (seconds, default `60.0`),
`max_retries` (default `2`), `http_client=`/`transport=` (inject or mock the underlying
httpx2 client), and `limits=` (connection pool limits, default `max_connections=100,
max_keepalive_connections=50`).

**Both must be closed** to release their connection pool — use them as a context manager
(`with sp.Client() as client:` / `async with sp.AsyncClient() as client:`) or call
`client.close()` / `await client.aclose()` explicitly. The old `requests.Session`-backed
clients didn't require this.

## Deprecated (still works, now warns): per-resource `Client()`

`amzn_selling_partner.reports.Client()` and `amzn_selling_partner.vendor.orders.Client()`
still exist with the same constructor kwargs and the same public methods, but now emit a
`DeprecationWarning` and internally delegate to a `Client` they construct. Prefer
`sp.Client(...).reports` / `sp.Client(...).vendor.orders` going forward.

## Removed (not shimmed): `amzn_selling_partner.client.auth`

`ClientSessionAuth`, `ClientSessionAuthAccessToken`, `ClientSessionAuthTemporaryCredentials`,
and their `*Error` classes are gone, along with `BaseClient().http_session`. These were
internal wiring for the `requests`-based auth hook, never documented public API beyond the
endpoint-string helpers — `amzn_selling_partner.client.BaseClient` keeps only
`get_api_endpoint()` / `get_resource_path()` / `get_resource_endpoint()` /
`get_operation_endpoint()` (also now deprecated in favor of `Client`/`AsyncClient`). If you
were reaching into the removed classes directly, there is no replacement — construct a
`Client`/`AsyncClient` instead and let it manage auth internally.

## New: automatic retries

Requests now automatically retry on `408/409/429/500/502/503/504` responses and on
connection/timeout errors, up to `max_retries` times (default `2`), with exponential backoff
and jitter that honors a `Retry-After` header when present. Pass `max_retries=0` to a
`Client`/`AsyncClient` to restore the old (no automatic retry) behavior exactly.

## New: error hierarchy

Errors now raise from `amzn_selling_partner._exceptions`: `APIStatusError` (with `.response`,
`.status_code`, `.body`) and its per-status subclasses (`BadRequestError`,
`AuthenticationError`, `PermissionDeniedError`, `NotFoundError`, `ConflictError`,
`UnprocessableEntityError`, `RateLimitError`, `InternalServerError`) for HTTP error responses;
`APIConnectionError`/`APITimeoutError` for network/timeout failures. Previously, `requests`'
own `HTTPError`/`ConnectionError`/`Timeout` propagated directly — catch the new types instead.

## New: `with_raw_response`

Every resource exposes `.with_raw_response`, returning the raw `httpx2.Response` instead of a
parsed pydantic model — e.g. `client.reports.with_raw_response.get_report(...)`. **Asymmetry
to note:** `with_raw_response.create_report(...)` returns only the initial `POST reports`
response; the parsed `create_report()` additionally performs a follow-up `GET report` and
returns *that* result, which `with_raw_response` does not replicate.

## Pydantic v1 → v2

All request/response models (in `reports.models` and `vendor.orders.models`) are now pydantic
v2 `BaseModel`s. User-visible effects:

- `.dict()` → `.model_dump()`, `.json()` → `.model_dump_json()`, `.copy()` → `.model_copy()`.
  The old v1 methods still exist as deprecated compatibility shims in pydantic v2 and continue
  to work, but emit deprecation warnings — update call sites when convenient.
- Validation errors now raise `pydantic.ValidationError` in v2's format (different `.errors()`
  structure than v1). If you catch `pydantic.v1.error_wrappers.ValidationError` specifically,
  switch to plain `pydantic.ValidationError`.
- Unknown/extra fields on response models are still silently ignored (pydantic v1's default,
  preserved deliberately for forward-compatibility with SP-API responses that add fields over
  time) — `ReportOptions` remains the one model that rejects extra fields (`extra="forbid"`),
  matching its v1 behavior.
- The `pydantic` dependency pin moves from an exact `==1.10.13` to a range `>=2,<3` — a
  deliberate, minor deviation from this repo's usual exact-pin convention, since pinning a
  fast-moving major version exactly would create constant busywork for a change this small.

## Dependencies

- Removed: `requests`, `requests_aws4auth`.
- Added: `httpx2` (runtime dependency).
- New optional extra `aiohttp` (`aiohttp[speedups]`, `httpx_aiohttp[httpx2]`): when installed,
  `AsyncClient` automatically uses an aiohttp-backed transport instead of httpx2's default.
  Install with `uv sync --extra aiohttp` (or `pip install amzn-selling-partner[aiohttp]`).
- New dev-only dependencies: `unasync` (generates the sync resource classes from their async
  source — see `scripts/generate_sync.py`) and `pytest-asyncio` (async test support). Neither
  ships to end users.

## Testing: `responses` → `httpx2.MockTransport`

This repo's own test suite no longer uses the `responses` library (which patches `requests`
globally and has no equivalent for `httpx2`). If your own tests mocked this SDK's HTTP calls
via `responses`, that will stop working — switch to `httpx2.MockTransport`, passed as
`transport=` to `Client`/`AsyncClient`:

```python
import httpx2
import amzn_selling_partner as sp

def handler(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, json={"reportId": "report-1"})

client = sp.Client(transport=httpx2.MockTransport(handler), ...)
```

Note that this SDK's auth flow performs its own LWA token-refresh HTTP call through the same
transport — a `MockTransport` handler needs to also answer `POST
https://api.amazon.com/auth/o2/token` (see `tests/conftest.py`'s `with_lwa()` helper in this
repo for the pattern).

## Known limitation: async credential refresh runs in a thread

`AsyncClient`'s AWS SigV4 signing and STS `assume_role` credential refresh are backed by
`boto3`/`botocore`, which are synchronous under the hood. To avoid blocking the event loop,
these are offloaded via `asyncio.to_thread` inside the async auth flow. This means each
credential refresh briefly occupies a thread-pool worker; if you run many concurrent
`AsyncClient`s with a constrained thread pool, size `asyncio`'s default executor accordingly.
This is a known limitation, not a bug — there is no async-native AWS SDK in use here.

## Python version support unchanged

`requires-python` stays `>=3.10`. Request timeouts are enforced via httpx2's own per-request
`timeout=` configuration (not `asyncio.timeout()`, which needs Python 3.11+), matching the
approach used by the OpenAI Python SDK — so Python 3.10 remains fully supported.
