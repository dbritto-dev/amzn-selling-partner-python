# Amazon Selling Partner Python Library

The Amazon Selling Partner Python library provides convenient access to the Amazon Selling Partner
API from applications written in the Python language. It includes a pre-defined set of classes for
API resources and it is compatible with the latest versions of the Amazon Selling Partner API.

- **Discussions:** https://github.com/dbritto-dev/amzn-selling-partner-python/discussions
- **Bug reports:** https://github.com/dbritto-dev/amzn-selling-partner-python/issues
- **Source code:** https://github.com/dbritto-dev/amzn-selling-partner-python

# Documentation

- Tutorial: https://developer-docs.amazon.com/sp-api/docs/tutorial-create-a-private-selling-partner-api-application
- AWS Lambda Demo: https://github.com/aws-quickstart/quickstart-amazon-selling-partner-api/blob/main/functions/source/ExampleLambda/lambda_function.py
- Get AWS secret keys: https://docs.aws.amazon.com/powershell/latest/userguide/pstools-appendix-sign-up.html
- Reports Tutorial: https://developer-docs.amazon.com/sp-api/docs/reports-api-v2021-06-30-tutorial-request-a-report
- Report Types for Vendor: https://developer-docs.amazon.com/sp-api/docs/report-type-values-analytics#vendor-retail-analytics-reports
- Market Place Ids: https://developer-docs.amazon.com/sp-api/docs/marketplace-ids
- API Endpoints and Regions: https://developer-docs.amazon.com/sp-api/docs/sp-api-endpoints
- API Endpoints and Regions (Sandbox): https://developer-docs.amazon.com/sp-api/docs/the-selling-partner-api-sandbox

## Installation

### Install with uv

```sh
uv sync
```

Install the development tools with:

```sh
uv sync --extra dev
```

### Install from a GitHub private repo

```sh
TOKEN="<token>" pip install git+https://dbritto-dev:$TOKEN@github.com/dbritto-dev/amzn-selling-partner-python.git
```

### Install from source

```sh
uv pip install .
```

## Requirements

- Python 3.10 or later (PyPy supported)

## Usage

This library needs to be configure with your account's secret keys: Selling Partner Keys and AWS
Keys.

Set up the next environment variables. We can use [dotenv](https://pypi.org/project/python-dotenv/)
to load them locally.

```
# Fetch "client id" and "client secret" from your application in Seller Central
# by clicking on "View" in front of your application ID.
SELLING_PARTNER_APP_CLIENT_ID=
SELLING_PARTNER_APP_CLIENT_SECRET=
# In order to call an API for a seller, you will need to paste the
# refresh_token for that particular seller below. You can get refresh token for
# a seller using OAuth flow. Otherwise, you can self-authorize your application
# by clicking on "Authorize" from the dropdown menu in front of your
# application ID in seller central. Once you click on "Generate Refresh Token",
# you would be able to receive a refresh token and paste it below.
SELLING_PARTNER_APP_REFRESH_TOKEN=
# Pull out "access key ID" and "secret access key" from IAM console by cliking on
# "Users" navigation menu option and opening "Security Credentials" tab.
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
# This role is necessary to create temporary credentials to the call Selling Partner API, to read
# more about which policies and resources are needed for this role, here's the link (click on ->
# `Select to expand the manual steps to create and configure IAM policies.` to read more about that)
# https://developer-docs.amazon.com/sp-api/docs/tutorial-create-a-private-selling-partner-api-application#step-3-create-and-configure-iam-resources
# The role session name is just the label that we set up for those temporary credentials
AWS_SELLING_PARTNER_ROLE=
AWS_SELLING_PARTNER_ROLE_SESSION_NAME=
```

```python
import amzn_selling_partner as sp

client = sp.Client()

purchase_orders = client.vendor.orders.get_purchase_orders()
print(purchase_orders)

purchase_order = client.vendor.orders.get_purchase_order("<purchase-order-number>")
print(purchase_order)
```

An async client is available too, with the same resources and method signatures:

```python
import asyncio

import amzn_selling_partner as sp


async def main() -> None:
    async with sp.AsyncClient() as client:
        purchase_orders = await client.vendor.orders.get_purchase_orders()
        print(purchase_orders)


asyncio.run(main())
```

`Client`/`AsyncClient` manage an HTTP connection pool and should be closed when you're done with
them — use them as a context manager (as above), or call `client.close()` /
`await client.aclose()` explicitly.

> **Note:** `amzn_selling_partner.reports.Client()` and `amzn_selling_partner.vendor.orders.Client()`
> (constructing a client per resource, without a region/sandbox namespace) still work but are
> deprecated in favor of `sp.Client()`/`sp.AsyncClient()`. See [MIGRATION.md](MIGRATION.md).

### Handling exceptions

Unsuccessful requests raise one of the exceptions in `amzn_selling_partner._exceptions`:
`APIStatusError` (and its per-status subclasses, e.g. `RateLimitError`, `NotFoundError`) for HTTP
error responses, or `APIConnectionError`/`APITimeoutError` for network/timeout failures. Requests
are automatically retried on `429`/`5xx` responses and connection/timeout errors (honoring
`Retry-After`) up to `max_retries` times (default `2`); pass `max_retries=0` to disable retries.

### Per-client configuration

Configure a client with keyword arguments. For instance, you can make requests against a specific
[selling partner region](https://developer-docs.amazon.com/sp-api/docs/sp-api-endpoints), enable
sandbox mode, or tune HTTP behavior:

```python
import amzn_selling_partner as sp

na_client = sp.Client(selling_partner_region=sp.SellingPartnerRegion.NORTH_AMERICA)
eu_client = sp.Client(selling_partner_region=sp.SellingPartnerRegion.EUROPE)
fe_client = sp.Client(selling_partner_region=sp.SellingPartnerRegion.FAR_EAST)

sandbox_client = sp.Client(sandbox=True)

tuned_client = sp.Client(timeout=30.0, max_retries=0)
```

> **Note:** some endpoints are not available on sandbox. To read more about that: https://developer-docs.amazon.com/sp-api/docs/the-selling-partner-api-sandbox

### Optional aiohttp transport

`AsyncClient` uses httpx2's default async transport unless the `aiohttp` extra is installed, in
which case it automatically uses an aiohttp-backed transport instead:

```sh
uv sync --extra aiohttp
```

## Development

### Install from source

```sh
uv sync --extra dev
```

### Type checking

```sh
uv run ty check src/amzn_selling_partner
```

### Lint and format

```sh
uv run nox -s lint
```

### Test

```sh
uv run nox -s test
```

### Security checks

```sh
uv run nox -s security_test
```

### CI

Lint, tests, type checking, and security checks run automatically on every push and pull request
via [GitHub Actions](.github/workflows/ci.yml), across Python 3.10 through 3.13.
