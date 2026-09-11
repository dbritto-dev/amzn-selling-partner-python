from __future__ import annotations

import asyncio
import gzip
import json
import pathlib
import re
import threading
import time
from typing import Any

import httpx2
import pytest

from amzn_selling_partner import AuthenticationError, RequestOptions
from amzn_selling_partner.plugins._amazon.pagination import DROP_PARAMS_ON_NEXT, OVERRIDES
from amzn_selling_partner.plugins._amazon.rdt import GRANTLESS, RESTRICTED
from amzn_selling_partner.plugins.amazon_spapi import (
    AsyncLWAAuth,
    AsyncSellingPartner,
    LWAAuth,
    LWACredentials,
    Marketplace,
    Region,
    SellingPartner,
    default_spec_dir,
    parse_rate_limit,
    with_rdt,
)
from amzn_selling_partner.runtime._throttle import RateLimit, TokenBucket
from amzn_selling_partner.spec import load_document

from ._amazon_mock import AmazonMock
from .conftest import AMAZON_MODELS, requires_amazon

pytestmark = requires_amazon

CREDS = LWACredentials(client_id="cid", client_secret="sec", refresh_token="rt")


def sp(mock: AmazonMock, **kw: Any) -> SellingPartner:
    kw.setdefault("credentials", CREDS)
    kw.setdefault("throttle", False)
    kw.setdefault("backoff_initial", 0.0001)
    return SellingPartner(transport=mock.transport(), **kw)


def asp(mock: AmazonMock, **kw: Any) -> AsyncSellingPartner:
    kw.setdefault("credentials", CREDS)
    kw.setdefault("throttle", False)
    return AsyncSellingPartner(transport=mock.transport(), **kw)


# -- rate limits ---------------------------------------------------------------------------


def test_parse_rate_limit_formats() -> None:
    two = "text\n\n**Usage Plan:**\n\n| Rate (requests per second) | Burst |\n| ---- | ---- |\n| 0.0167 | 20 |\n\nmore"
    three = "| Plan type | Rate (requests per second) | Burst |\n| ---- | ---- | ---- |\n|Default| 5 | 10 |\n|Selling partner specific| Variable | Variable |\n"
    placeholder = "| Rate (requests per second) | Burst |\n| ---- | ---- |\n| n | n |\n"
    assert parse_rate_limit(two) == RateLimit(rate=0.0167, burst=20)
    assert parse_rate_limit(three) == RateLimit(rate=5, burst=10)
    assert parse_rate_limit(placeholder) is None
    assert parse_rate_limit("no table") is None and parse_rate_limit(None) is None


def test_rate_limit_counts_across_pinned_specs() -> None:
    parsed = 0
    unparsed: list[str] = []
    for path in sorted(AMAZON_MODELS.glob("**/*.json")):
        doc = load_document(path)
        for op in doc.operations:
            if parse_rate_limit(op.description) is None:
                unparsed.append(f"{path.stem}.{op.operation_id}")
            else:
                parsed += 1
    assert parsed == 300
    assert len(unparsed) == 73, unparsed
    assert "fulfillmentInbound_2024-03-20.listPrepDetails" in unparsed  # placeholder table
    assert "definitionsProductTypes_2020-09-01.searchDefinitionsProductTypes" not in unparsed  # "Plan type" table


def test_client_reports_unparsed_rate_limits() -> None:
    client = sp(AmazonMock())
    client.orders.v0  # noqa: B018
    client.seller_wallet.latest  # noqa: B018
    assert client.unparsed_rate_limits["orders.v0"] == []
    assert len(client.unparsed_rate_limits["seller_wallet.v2024_03_01"]) == 12
    assert client.orders.v0.operation("getOrders").rate_limit == RateLimit(rate=0.0167, burst=20)


# -- annotations: rdt, grantless, pagination -------------------------------------------------


def _ops_index() -> dict[tuple[str, str], set[str]]:
    from amzn_selling_partner.plugins._amazon.naming import api_naming

    index: dict[tuple[str, str], set[str]] = {}
    for path in AMAZON_MODELS.glob("**/*.json"):
        named = api_naming(path)
        assert named is not None, path
        index[named] = {op.operation_id for op in load_document(path).operations}
    return index


def test_restricted_and_grantless_tables_reference_real_operations() -> None:
    index = _ops_index()
    for api, version, op_id in RESTRICTED:
        versions = [v for (a, v) in index if a == api and (version is None or v == version)]
        assert versions, (api, version, op_id)
        assert any(op_id in index[(api, v)] for v in versions), (api, version, op_id)
    for api, op_id in GRANTLESS:
        assert any(op_id in ops for (a, _v), ops in index.items() if a == api), (api, op_id)
    for api, version, op_id in OVERRIDES:
        versions = [v for (a, v) in index if a == api and (version is None or v == version)]
        assert versions and any(op_id in index[(api, v)] for v in versions), (api, version, op_id)


def test_grantless_table_matches_descriptions() -> None:
    from amzn_selling_partner.plugins._amazon.naming import api_naming

    found: set[tuple[str, str]] = set()
    for path in AMAZON_MODELS.glob("**/*.json"):
        api, _ = api_naming(path)  # type: ignore[misc]
        for op in load_document(path).operations:
            if re.search(r"grantless", op.description or "", re.I):
                found.add((api, op.operation_id))
    assert found <= set(GRANTLESS)
    assert set(GRANTLESS) - found == {("application", "rotateApplicationClientSecret")}


def test_drop_params_entries_have_token_params() -> None:
    index = _ops_index()
    for api, op_id in DROP_PARAMS_ON_NEXT:
        assert any(op_id in ops for (a, _v), ops in index.items() if a == api), (api, op_id)


def test_rdt_marking() -> None:
    client = sp(AmazonMock())
    orders = client.orders.v0
    assert orders.operation("getOrderAddress").annotations["rdt"].data_elements is None
    assert orders.operation("getOrders").annotations["rdt"].data_elements == ("buyerInfo", "shippingAddress", "buyerTaxInformation")
    assert "rdt" not in orders.operation("confirmShipment").annotations
    assert client.notifications.v1.operation("getDestinations").annotations["grantless_scopes"] == ("sellingpartnerapi::notifications",)
    assert "grantless_scopes" not in client.notifications.v1.operation("getSubscription").annotations


def test_pagination_annotations() -> None:
    client = sp(AmazonMock())
    orders = client.orders.v0
    p = orders.operation("getOrders").pagination
    assert p is not None and p.descriptor.drop_params_on_next and p.descriptor.items_path == "payload.Orders"
    listings = client.listings_items.v2021_08_01.operation("searchListingsItems").pagination
    assert (
        listings is not None
        and listings.descriptor.next_token_param == "pageToken"
        and listings.descriptor.prev_token_path == "pagination.previousToken"
    )
    fin = client.finances.v0.operation("listFinancialEvents").pagination
    assert fin is not None and fin.descriptor.items_is_object
    assert client.fba_inventory.v1.operation("getInventorySummaries").pagination is not None
    assert client.aplus_content.latest.operation("searchContentDocuments").pagination.descriptor.next_token_path == "nextPageToken"


def test_servers_and_regions() -> None:
    assert sp(AmazonMock()).base_url == "https://sellingpartnerapi-na.amazon.com"
    assert sp(AmazonMock(), region=Region.EU, sandbox=True).base_url == "https://sandbox.sellingpartnerapi-eu.amazon.com"
    assert sp(AmazonMock(), marketplace=Marketplace.JP).base_url == "https://sellingpartnerapi-fe.amazon.com"
    assert Marketplace("A1F83G8C2ARO7P") is Marketplace.UK and Marketplace.UK.region is Region.EU
    assert Region.NORTH_AMERICA is Region.NA and Region.NA.api_sandbox_endpoint.startswith("https://sandbox.")
    assert sp(AmazonMock()).options.request_id_header == "x-amzn-RequestId"


def test_naming_and_aliases() -> None:
    client = sp(AmazonMock())
    assert len(client.apis) == 55
    assert client.orders.versions == ["v0", "v2026_01_01"] and client.orders.latest.operation("searchOrders")
    assert client.invoices is client.invoices_api_model
    assert client.shipping.versions == ["v1", "v2"] and client.shipping.latest is client.shipping.v2
    assert "link_carrier_account_post" in dir(client.shipping.v2)
    assert client.catalog_items.versions == ["v0", "v2020_12_01", "v2022_04_01"]


# -- auth --------------------------------------------------------------------------------------


def test_lwa_refresh_flow_and_caching() -> None:
    mock = AmazonMock()
    client = sp(mock)
    client.orders.v0.get_order(order_id="1")
    client.orders.v0.get_order(order_id="2")
    assert mock.token_calls == 1
    token_req = mock.by_path("/auth/o2/token")[0]
    assert token_req.method == "POST" and "grant_type=refresh_token" in token_req.content.decode()
    assert token_req.headers["content-type"].startswith("application/x-www-form-urlencoded")
    assert mock.by_path("/orders/v0/orders/1")[0].headers["x-amz-access-token"] == "Atza|rt|1"


def test_lwa_token_expiry_triggers_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    mock = AmazonMock()
    mock.token_ttl = 100
    auth = LWAAuth(CREDS, transport=mock.transport())
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(time, "time", lambda: now["t"])
    assert auth.access_token() == "Atza|rt|1"
    now["t"] += 30
    assert auth.access_token() == "Atza|rt|1"
    now["t"] += 30  # within the 60s leeway of expiry
    assert auth.access_token() == "Atza|rt|2"
    assert mock.token_calls == 2


def test_lwa_single_flight_sync() -> None:
    mock = AmazonMock()
    gate = threading.Event()
    orig = mock.__call__

    def slow(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/token"):
            gate.wait(2)
        return orig(request)

    auth = LWAAuth(CREDS, transport=httpx2.MockTransport(slow))
    results: list[str] = []
    threads = [threading.Thread(target=lambda: results.append(auth.access_token())) for _ in range(8)]
    for t in threads:
        t.start()
    time.sleep(0.05)
    gate.set()
    for t in threads:
        t.join()
    assert mock.token_calls == 1 and set(results) == {"Atza|rt|1"}


def test_lwa_single_flight_async() -> None:
    mock = AmazonMock()
    orig = mock.__call__

    async def slow(request: httpx2.Request) -> httpx2.Response:
        if request.url.path.endswith("/token"):
            await asyncio.sleep(0.05)
        return orig(request)

    async def go() -> None:
        auth = AsyncLWAAuth(CREDS, transport=httpx2.MockTransport(slow))
        results = await asyncio.gather(*(auth.access_token() for _ in range(8)))
        assert set(results) == {"Atza|rt|1"} and mock.token_calls == 1
        await auth.aclose()

    asyncio.run(go())


def test_grantless_uses_client_credentials() -> None:
    mock = AmazonMock()
    client = sp(mock)
    client.notifications.v1.get_destinations()
    form = mock.by_path("/auth/o2/token")[0].content.decode()
    assert "grant_type=client_credentials" in form and "scope=sellingpartnerapi%3A%3Anotifications" in form
    assert mock.by_path("/destinations")[0].headers["x-amz-access-token"] == "Atza|cc|1"
    client.orders.v0.get_order(order_id="1")
    assert mock.token_calls == 2  # separate cache entries per grant


def test_rdt_flow_sync_and_async() -> None:
    mock = AmazonMock()
    client = sp(mock)
    client.orders.v0.get_order_address(order_id="902-1")
    rdt_req = mock.by_path("/restrictedDataToken")[0]
    assert json.loads(rdt_req.content) == {"restrictedResources": [{"method": "GET", "path": "/orders/v0/orders/902-1/address"}]}
    assert rdt_req.headers["x-amz-access-token"] == "Atza|rt|1"
    assert mock.by_path("/address")[0].headers["x-amz-access-token"] == "RDT|GET|/orders/v0/orders/902-1/address|"
    # cached per resource
    client.orders.v0.get_order_address(order_id="902-1")
    assert mock.rdt_calls == 1
    # dataElements only when requested
    client.orders.v0.get_orders(marketplace_ids=["ATVPDKIKX0DER"], created_after="2020-01-01T00:00:00Z")
    assert mock.by_path("/orders/v0/orders")[-1].headers["x-amz-access-token"] == "Atza|rt|1"
    client.orders.v0.get_orders(
        marketplace_ids=["ATVPDKIKX0DER"], created_after="2020-01-01T00:00:00Z", request_options=with_rdt("buyerInfo", "shippingAddress")
    )
    assert mock.rdt_calls == 2
    assert json.loads(mock.by_path("/restrictedDataToken")[-1].content)["restrictedResources"][0]["dataElements"] == [
        "buyerInfo",
        "shippingAddress",
    ]
    assert mock.by_path("/orders/v0/orders")[-1].headers["x-amz-access-token"].startswith("RDT|GET|/orders/v0/orders|buyerInfo")
    # explicit token header wins
    client.orders.v0.get_order(order_id="9", request_options=RequestOptions(extra_headers={"x-amz-access-token": "MINE"}))
    assert [r for r in mock.requests if r.url.path == "/orders/v0/orders/9"][0].headers["x-amz-access-token"] == "MINE"

    async def go() -> None:
        amock = AmazonMock()
        aclient = asp(amock)
        await aclient.orders.v0.get_order_address(order_id="1")
        assert amock.rdt_calls == 1 and amock.by_path("/address")[0].headers["x-amz-access-token"].startswith("RDT|")
        await aclient.aclose()

    asyncio.run(go())


def test_auth_failure_maps_to_authentication_error() -> None:
    mock = AmazonMock()
    mock.fail_token = True
    with pytest.raises(AuthenticationError) as ei:
        sp(mock).orders.v0.get_order(order_id="1")
    assert ei.value.status_code == 400 and ei.value.body["error"] == "invalid_grant"


def test_pluggable_token_store_and_no_credentials() -> None:
    class DictStore:
        def __init__(self) -> None:
            self.data: dict[str, Any] = {}

        def get(self, key: str) -> Any:
            return self.data.get(key)

        def set(self, key: str, token: Any) -> None:
            self.data[key] = token

    store = DictStore()
    mock = AmazonMock()
    sp(mock, token_store=store).orders.v0.get_order(order_id="1")
    assert len(store.data) == 1 and next(iter(store.data)).startswith("lwa:refresh:")
    mock2 = AmazonMock()
    client = SellingPartner(transport=mock2.transport(), throttle=False, credentials=None)
    client.orders.v0.get_order(order_id="1")
    assert "x-amz-access-token" not in mock2.requests[0].headers and mock2.token_calls == 0


def test_credentials_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELLING_PARTNER_APP_CLIENT_ID", "envid")
    monkeypatch.setenv("SELLING_PARTNER_APP_CLIENT_SECRET", "envsec")
    monkeypatch.setenv("SELLING_PARTNER_APP_REFRESH_TOKEN", "envrt")
    mock = AmazonMock()
    SellingPartner(transport=mock.transport(), throttle=False).orders.v0.get_order(order_id="1")
    assert "refresh_token=envrt" in mock.by_path("/auth/o2/token")[0].content.decode()


# -- pagination + throttling through the real specs -------------------------------------------


def test_orders_pagination_walk_with_drop_params_and_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    acquires: list[str] = []
    orig = TokenBucket.acquire

    def counting(self: TokenBucket) -> float:
        acquires.append("x")
        return orig(self)

    monkeypatch.setattr(TokenBucket, "acquire", counting)
    mock = AmazonMock()
    client = sp(mock, throttle=True)
    page = client.orders.v0.get_orders(marketplace_ids=["ATVPDKIKX0DER"], created_after="2020-01-01T00:00:00Z", max_results_per_page=1)
    ids = [o.amazon_order_id for o in page]
    assert ids == ["902-1", "902-2", "902-3"]
    urls = [str(r.url) for r in mock.by_path("/orders/v0/orders")]
    assert urls[0].endswith("?CreatedAfter=2020-01-01T00%3A00%3A00Z&MarketplaceIds=ATVPDKIKX0DER&MaxResultsPerPage=1")
    assert urls[1].endswith("/orders/v0/orders?NextToken=n2") and urls[2].endswith("?NextToken=n3")
    assert len(acquires) == 3  # one bucket acquire per page

    async def go() -> list[str]:
        aclient = asp(AmazonMock())
        p = await aclient.orders.v0.get_orders(marketplace_ids=["ATVPDKIKX0DER"], created_after="2020-01-01T00:00:00Z")
        return [o.amazon_order_id async for o in p]

    assert asyncio.run(go()) == ["902-1", "902-2", "902-3"]


def test_raw_mode_and_request_id() -> None:
    mock = AmazonMock()
    client = sp(mock)
    raw = client.orders.v0.get_orders(marketplace_ids=["ATVPDKIKX0DER"], created_after="2020-01-01T00:00:00Z", raw=True)
    assert raw.raw["payload"]["Orders"][0]["AmazonOrderId"] == "902-1"
    assert [o["AmazonOrderId"] for o in raw] == ["902-1", "902-2", "902-3"]
    with pytest.raises(Exception) as ei:
        client.orders.v0.get_order_items(order_id="missing")
    assert getattr(ei.value, "request_id", None) == "req-404"


# -- documents ---------------------------------------------------------------------------------


def test_document_download_gzip_and_upload(tmp_path: pathlib.Path) -> None:
    mock = AmazonMock()
    client = sp(mock)
    assert client.documents.download_report("doc-1") == mock.report_bytes
    target = tmp_path / "report.tsv"
    assert client.documents.download_report("doc-1", path=target) == len(mock.report_bytes)
    assert target.read_bytes() == mock.report_bytes
    assert "x-amz-access-token" not in mock.by_path("/report.gz")[0].headers
    # restricted report type -> RDT on getReportDocument
    client.documents.download_report("doc-1", report_type="GET_FLAT_FILE_ORDER_REPORT_DATA_SHIPPING")
    assert (
        mock.by_path("/reports/2021-06-30/documents/doc-1")[-1].headers["x-amz-access-token"]
        == "RDT|GET|/reports/2021-06-30/documents/doc-1|"
    )
    assert mock.by_path("/reports/2021-06-30/documents/doc-1")[0].headers["x-amz-access-token"].startswith("Atza|")
    feed = client.documents.create_feed("POST_PRODUCT_DATA", ["ATVPDKIKX0DER"], "<xml/>", content_type="text/xml; charset=UTF-8")
    assert feed.feed_id == "f-1"
    upload = mock.by_path("/upload")[0]
    assert upload.method == "PUT" and upload.headers["content-type"] == "text/xml; charset=UTF-8" and upload.content == b"<xml/>"

    async def go() -> None:
        amock = AmazonMock()
        aclient = asp(amock)
        assert await aclient.documents.download_report("doc-1") == amock.report_bytes
        out = tmp_path / "async.tsv"
        assert await aclient.documents.download_report("doc-1", path=out) == len(amock.report_bytes)
        assert out.read_bytes() == amock.report_bytes
        assert (
            await aclient.documents.create_feed("POST_PRODUCT_DATA", ["ATVPDKIKX0DER"], b"<xml/>", content_type="text/xml")
        ).feed_id == "f-1"
        await aclient.aclose()

    asyncio.run(go())


def test_download_already_decoded_by_transport() -> None:
    from amzn_selling_partner.plugins._amazon.documents import download_document

    def handler(r: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, content=gzip.compress(b"data"), headers={"Content-Encoding": "gzip"})

    with httpx2.Client(transport=httpx2.MockTransport(handler)) as http:
        assert download_document("https://x/doc", compression="GZIP", http_client=http) == b"data"


# -- notifications ------------------------------------------------------------------------------


def test_notification_models() -> None:
    client = sp(AmazonMock())
    models = client.notifications_models
    assert "OrderChangeNotification" in models.names
    schema_dir = models.schema_dir
    payload = json.loads((schema_dir / "OrderChangeNotification.json").read_text())["examples"][0]
    parsed = models.parse(json.dumps(payload).encode())
    assert type(parsed).__name__ == "OrderChangeNotification"
    assert parsed.payload.order_change_notification.amazon_order_id == payload["Payload"]["OrderChangeNotification"]["AmazonOrderId"]
    assert models.model("ListingsItemIssuesChangeNotification_2023-12-13").__name__ == "ListingsItemIssuesChangeNotification_2023_12_13"
    # Known irregularities in the pinned schemas (see docs/PLAN.md §10):
    # - ShipmentTrackingMilestoneChangedNotification.json is a dangling "$ref": "#/definitions/Notification"
    # - ListingsItemStatusChangeNotification.json's own example says LISTINGS_ITEM_STATUS_CHANGE
    #   while the schema enum says LISTINGS_ITEM_STATUS_CHANGED
    # (B2bAnyOfferChangedNotification.json spells its root reference "#ref"; the loader accepts it)
    known_bad = {"ShipmentTrackingMilestoneChangedNotification", "ListingsItemStatusChangeNotification"}
    failures: list[str] = []
    for name in models.names:  # every schema builds and validates its own examples
        try:
            model = models.model(name)
            for example in json.loads((schema_dir / f"{name}.json").read_text()).get("examples", []):
                model.model_validate(example)
        except Exception as exc:  # noqa: BLE001
            failures.append(name)
            if name not in known_bad:
                raise AssertionError(f"{name}: {str(exc).splitlines()[0]}") from exc
    assert set(failures) == known_bad


# -- sandbox ----------------------------------------------------------------------------------------


def test_sandbox_examples_exposed() -> None:
    client = sp(AmazonMock())
    examples = client.sandbox_examples(client.orders.v0.get_orders)
    assert examples and examples[0].status == 200 and examples[0].parameters["MarketplaceIds"] == ["ATVPDKIKX0DER"]
    assert any(e.status == 400 for e in examples)
    assert client.sandbox_examples(client.orders.v0.confirm_shipment)[0].has_body
    assert client.shipping.v2.operation("getRates").annotations.get("sandbox_dynamic") is True
    vs = client.vendor_shipments.v1
    sources = {e.source for name in vs.operations for e in vs.operation(name).annotations.get("sandbox_examples", ())}
    assert "x-amazon-spds-sandbox-behaviors" in sources


@pytest.mark.parametrize("api", ["orders", "listings_items"])
def test_sandbox_runner(api: str) -> None:
    from amzn_selling_partner import sandbox_tests

    def sync_factory(transport: httpx2.MockTransport | None) -> Any:
        return SellingPartner(transport=transport, sandbox=True, throttle=False, max_retries=0, credentials=None)

    def async_factory(transport: httpx2.MockTransport | None) -> Any:
        return AsyncSellingPartner(transport=transport, sandbox=True, throttle=False, max_retries=0, credentials=None)

    outcomes = sandbox_tests.run(sync_factory, async_factory, [api])
    failures = [f"{o.mode} {o.case.version}.{o.case.operation_id}[{o.case.status}]: {o.error}" for o in outcomes if not o.ok]
    ops = {o.case.operation_id for o in outcomes}
    expected = {
        op.operation_id
        for path in AMAZON_MODELS.glob(f"{'orders-api-model' if api == 'orders' else 'listings-items-api-model'}/*.json")
        for op in load_document(path).operations
    }
    assert ops == expected
    assert not failures, "\n".join(failures)


def test_default_spec_dir_exists() -> None:
    assert default_spec_dir().is_dir()
