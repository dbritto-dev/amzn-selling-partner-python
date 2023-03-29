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
- Report Types for Vendor: https://developer-docs.amazon.com/sp-api/docs/report-type-values#vendor-retail-analytics-reports
- Market Place Ids: https://developer-docs.amazon.com/sp-api/docs/marketplace-ids
- API Endpoints and Regions: https://developer-docs.amazon.com/sp-api/docs/sp-api-endpoints
- API Endpoints and Regions (Sandbox): https://developer-docs.amazon.com/sp-api/docs/the-selling-partner-api-sandbox

## Installation

### Create Virtual Environment

```sh
python3 -m pip install virtualenv
```

### Enable Virtual Environment

For Linux and OS X

```sh
. ./venv/bin/activate
```

For Windows

```sh
. ./venv/Scripts/activate
```

### Upgrade PIP

```sh
python -m pip install --upgrade pip
```

### Install from a GitHub private repo

```sh
TOKEN="<token>" pip install git+https://dbritto-dev:$TOKEN@github.com/dbritto-dev/amzn-selling-partner-python.git
```

### Install from source

```sh
pip install .
```

## Requirements

- Python 3.9 (PyPy supported)

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
import amzn_selling_partner.vendor as sp

sp_vendor_orders_client = sp.vendor.orders.Client()

purchase_orders = sp_vendor_orders_client.get_purchase_orders()
print(purchase_orders)

purchase_order = sp_vendor_orders_client.get_purchase_order("<purchase-order-number>")
print(purchase_order)
```

### Handling exceptions

Unsuccessful requests raise exceptions. The errors should handled as `Requests` library exceptions.
To read more about that: https://requests.readthedocs.io/en/latest/user/quickstart/#errors-and-exceptions

### Per-client configuration

Configure individual clients with keyword arguments. For instance, you can make a request with a
specific [selling partner region](https://developer-docs.amazon.com/sp-api/docs/sp-api-endpoints) or
use sandbox.

```python
import amzn_selling_partner.vendor as sp

na_sp_vendor_orders_client = sp.vendor.orders.Client(
    selling_partner_region=client.SellingPartnerRegion.NORTH_AMERICA
)

eu_sp_vendor_orders_client = sp.vendor.orders.Client(
    selling_partner_region=client.SellingPartnerRegion.EUROPE
)

fe_sp_vendor_orders_client = sp.vendor.orders.Client(
    selling_partner_region=client.SellingPartnerRegion.FAR_EAST
)
```

### Enable Sandbox

```python
import amzn_selling_partner.vendor as sp

sp_vendor_orders_client = sp.vendor.orders.Client(sandbox=True)
```

> **Note:** some endpoints are not available on sandbox. To read more about that: https://developer-docs.amazon.com/sp-api/docs/the-selling-partner-api-sandbox

## Development

### Install from source

```sh
pip install .[dev]
```
