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
from amzn_selling_partner._naming import api_version_of
from amzn_selling_partner.plugins._amazon.rdt import GRANTLESS, RESTRICTED
from amzn_selling_partner.plugins.amazon_spapi import (
    AsyncLWAAuth,
    AsyncSellingPartner,
    LWAAuth,
    LWACredentials,
    Marketplace,
    Region,
    SellingPartner,
    restricted_for,
    unparsed_rate_limits,
    with_rdt,
)
from amzn_selling_partner.sdk._http import REQUEST_ID_HEADER, RequestContext, TokenBucket
from amzn_selling_partner.sdk.resources import OPERATIONS, SERVICES

from ._amazon_mock import AmazonMock
from ._sandbox_examples import is_dynamic_sandbox, sandbox_examples
from ._specs import default_schema_dir, default_spec_dir
from .conftest import requires_amazon
from .sandbox import load_documents, raw_operations

pytestmark = requires_amazon

CREDS = LWACredentials(client_id="cid", client_secret="sec", refresh_token="rt")


def sp(mock: AmazonMock, **kw: Any) -> SellingPartner:
    kw.setdefault("credentials", CREDS)
    kw.setdefault("throttle", False)
    return SellingPartner(transport=mock.transport(), **kw)


def asp(mock: AmazonMock, **kw: Any) -> AsyncSellingPartner:
    kw.setdefault("credentials", CREDS)
    kw.setdefault("throttle", False)
    return AsyncSellingPartner(transport=mock.transport(), **kw)


def _ctx(module: str, operation: str) -> RequestContext:
    return RequestContext(operation=operation, service=module, method="GET", path="/x", options=None)


def _ops() -> dict[tuple[str, str], set[str]]:
    """``(api, version) -> operationIds`` from the generated resources registry."""
    out: dict[tuple[str, str], set[str]] = {}
    for key in OPERATIONS:
        module, _, op_id = key.partition(".")
        av = api_version_of(module)
        assert av is not None, module
        out.setdefault(av, set()).add(op_id.split(":")[0])
    return out


# -- rate limits (parsed at generation time, see codegen/src/python/ratelimits.ts) -------------


def test_rate_limit_counts_across_pinned_specs() -> None:
    parsed = sum(1 for v in OPERATIONS.values() if v[4])
    unparsed = unparsed_rate_limits()
    assert parsed == 300
    assert sum(len(v) for v in unparsed.values()) == 73, unparsed
    assert "listPrepDetails" in unparsed["fulfillment_inbound_v2024_03_20"]  # placeholder table
    assert OPERATIONS["definitions_product_types_v2020_09_01.searchDefinitionsProductTypes"][4] is True  # "Plan type" table
    assert OPERATIONS["orders_v0.getOrders"][4] is True


def test_client_reports_unparsed_rate_limits_and_seeds_buckets() -> None:
    mock = AmazonMock()
    client = sp(mock, throttle=True)
    unparsed = client.unparsed_rate_limits()
    assert "orders_v0" not in unparsed
    assert len(unparsed["seller_wallet_v2024_03_01"]) == 12
    client.orders_v0.list_orders(marketplace_ids=["ATVPDKIKX0DER"], created_after="2020-01-01T00:00:00Z")
    bucket = client.http._throttler.bucket("orders_v0.getOrders", None)
    assert bucket is not None and bucket.rate == 0.0167  # the usage-plan table: 0.0167 rps, burst 20


# -- tables: rdt, grantless, pagination ---------------------------------------------------------


def test_restricted_and_grantless_tables_reference_real_operations() -> None:
    index = _ops()
    for api, version, op_id in RESTRICTED:
        versions = [v for (a, v) in index if a == api and (version is None or v == version)]
        assert versions, (api, version, op_id)
        assert any(op_id in index[(api, v)] for v in versions), (api, version, op_id)
    for api, op_id in GRANTLESS:
        assert any(op_id in ops for (a, _v), ops in index.items() if a == api), (api, op_id)


def test_grantless_table_matches_descriptions() -> None:
    found: set[tuple[str, str]] = set()
    for (api, _version), document in load_documents().items():
        for op_id, raw in raw_operations(document).items():
            if re.search(r"grantless", str(raw.get("description") or ""), re.I):
                found.add((api, op_id))
    assert found <= set(GRANTLESS)
    assert set(GRANTLESS) - found == {("application", "rotateApplicationClientSecret")}


def test_registry_matches_pinned_specs() -> None:
    assert len(SERVICES) == 67 and len(OPERATIONS) == 373
    docs = load_documents()
    assert set(_ops()) == set(docs)
    for (api, version), op_ids in _ops().items():
        assert op_ids == set(raw_operations(docs[(api, version)])), (api, version)
    assert sum(1 for v in OPERATIONS.values() if v[3]) == 69  # paginated operations
    for key in (
        "orders_v0.getOrders",
        "listings_items_v2021_08_01.searchListingsItems",
        "finances_v0.listFinancialEvents",
        "fba_inventory_v1.getInventorySummaries",
        "aplus_content_v2020_11_01.searchContentDocuments",
    ):
        assert OPERATIONS[key][3] is True, key
    assert OPERATIONS["shipping_v2.linkCarrierAccount"][1:3] == ("POST", "/shipping/v2/carrierAccounts/{carrierId}")
    assert OPERATIONS["shipping_v2.linkCarrierAccount:PUT"][0] == "update_carrier_account"  # duplicate operationId in the spec


def test_iter_helpers_for_drop_params_operations() -> None:
    client = sp(AmazonMock())
    for key in ("orders_v0.getOrders", "reports_v2021_06_30.getReports", "feeds_v2021_06_30.getFeeds", "finances_v0.listFinancialEvents"):
        module, _, op_id = key.partition(".")
        method = OPERATIONS[key][0]
        assert callable(getattr(getattr(client, module), f"iter_{method}")), key


def test_rdt_marking() -> None:
    assert restricted_for("orders", "v0", "getOrderAddress").data_elements is None  # type: ignore[union-attr]
    assert restricted_for("orders", "v0", "getOrders").data_elements == ("buyerInfo", "shippingAddress", "buyerTaxInformation")  # type: ignore[union-attr]
    assert restricted_for("orders", "v0", "confirmShipment") is None
    req = httpx2.Request("GET", "https://x/")
    assert LWAAuth.classify(_ctx("orders_v0", "getOrderAddress"), req) == ("rdt", ())
    assert LWAAuth.classify(_ctx("orders_v0", "getOrders"), req) == ("lwa", ())
    assert LWAAuth.classify(_ctx("notifications_v1", "getDestinations"), req) == ("grantless", ("sellingpartnerapi::notifications",))
    assert LWAAuth.classify(_ctx("notifications_v1", "getSubscription"), req) == ("lwa", ())


def test_servers_and_regions() -> None:
    assert sp(AmazonMock()).base_url == "https://sellingpartnerapi-na.amazon.com"
    assert sp(AmazonMock(), region=Region.EU, sandbox=True).base_url == "https://sandbox.sellingpartnerapi-eu.amazon.com"
    assert sp(AmazonMock(), marketplace=Marketplace.JP).base_url == "https://sellingpartnerapi-fe.amazon.com"
    assert Marketplace("A1F83G8C2ARO7P") is Marketplace.UK and Marketplace.UK.region is Region.EU
    assert Region.NORTH_AMERICA is Region.NA and Region.NA.api_sandbox_endpoint.startswith("https://sandbox.")
    assert REQUEST_ID_HEADER == "x-amzn-RequestId"


def test_naming_and_aliases() -> None:
    client = sp(AmazonMock())
    assert client.orders is client.orders_v2026_01_01 and hasattr(client.orders, "list_orders")
    assert client.invoices is client.invoices_api_model_v2024_06_19
    assert client.shipping is client.shipping_v2 and client.shipping_v1 is not client.shipping_v2
    assert hasattr(client.shipping_v2, "update_carrier_account")  # PUT linkCarrierAccount (duplicate operationId)
    assert client.catalog_items is client.catalog_items_v2022_04_01
    assert client.product_pricing_v0.__class__.__name__ == "ProductPricingV0Resource"  # /products + /batches mounted together
    assert client.fba_inbound_eligibility is client.fba_inbound_v1 and client.awd is client.awd_v2024_05_09


# -- auth --------------------------------------------------------------------------------------


def test_lwa_refresh_flow_and_caching() -> None:
    mock = AmazonMock()
    client = sp(mock)
    client.orders_v0.get_order(order_id="1")
    client.orders_v0.get_order(order_id="2")
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
    client.notifications_v1.list_destinations()
    form = mock.by_path("/auth/o2/token")[0].content.decode()
    assert "grant_type=client_credentials" in form and "scope=sellingpartnerapi%3A%3Anotifications" in form
    assert mock.by_path("/destinations")[0].headers["x-amz-access-token"] == "Atza|cc|1"
    client.orders_v0.get_order(order_id="1")
    assert mock.token_calls == 2  # separate cache entries per grant


def test_rdt_flow_sync_and_async() -> None:
    mock = AmazonMock()
    client = sp(mock)
    client.orders_v0.list_order_address(order_id="902-1")
    rdt_req = mock.by_path("/restrictedDataToken")[0]
    assert json.loads(rdt_req.content) == {"restrictedResources": [{"method": "GET", "path": "/orders/v0/orders/902-1/address"}]}
    assert rdt_req.headers["x-amz-access-token"] == "Atza|rt|1"
    assert mock.by_path("/address")[0].headers["x-amz-access-token"] == "RDT|GET|/orders/v0/orders/902-1/address|"
    # cached per resource
    client.orders_v0.list_order_address(order_id="902-1")
    assert mock.rdt_calls == 1
    # dataElements only when requested
    client.orders_v0.list_orders(marketplace_ids=["ATVPDKIKX0DER"], created_after="2020-01-01T00:00:00Z")
    assert mock.by_path("/orders/v0/orders")[-1].headers["x-amz-access-token"] == "Atza|rt|1"
    client.orders_v0.list_orders(
        marketplace_ids=["ATVPDKIKX0DER"], created_after="2020-01-01T00:00:00Z", request_options=with_rdt("buyerInfo", "shippingAddress")
    )
    assert mock.rdt_calls == 2
    assert json.loads(mock.by_path("/restrictedDataToken")[-1].content)["restrictedResources"][0]["dataElements"] == [
        "buyerInfo",
        "shippingAddress",
    ]
    assert mock.by_path("/orders/v0/orders")[-1].headers["x-amz-access-token"].startswith("RDT|GET|/orders/v0/orders|buyerInfo")
    # explicit token header wins
    client.orders_v0.get_order(order_id="9", request_options=RequestOptions(extra_headers={"x-amz-access-token": "MINE"}))
    assert [r for r in mock.requests if r.url.path == "/orders/v0/orders/9"][0].headers["x-amz-access-token"] == "MINE"

    async def go() -> None:
        amock = AmazonMock()
        aclient = asp(amock)
        await aclient.orders_v0.list_order_address(order_id="1")
        assert amock.rdt_calls == 1 and amock.by_path("/address")[0].headers["x-amz-access-token"].startswith("RDT|")
        await aclient.aclose()

    asyncio.run(go())


def test_auth_failure_maps_to_authentication_error() -> None:
    mock = AmazonMock()
    mock.fail_token = True
    with pytest.raises(AuthenticationError) as ei:
        sp(mock).orders_v0.get_order(order_id="1")
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
    sp(mock, token_store=store).orders_v0.get_order(order_id="1")
    assert len(store.data) == 1 and next(iter(store.data)).startswith("lwa:refresh:")
    mock2 = AmazonMock()
    client = SellingPartner(transport=mock2.transport(), throttle=False, credentials=None)
    client.orders_v0.get_order(order_id="1")
    assert "x-amz-access-token" not in mock2.requests[0].headers and mock2.token_calls == 0


def test_credentials_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELLING_PARTNER_APP_CLIENT_ID", "envid")
    monkeypatch.setenv("SELLING_PARTNER_APP_CLIENT_SECRET", "envsec")
    monkeypatch.setenv("SELLING_PARTNER_APP_REFRESH_TOKEN", "envrt")
    mock = AmazonMock()
    SellingPartner(transport=mock.transport(), throttle=False).orders_v0.get_order(order_id="1")
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
    ids = [
        o.amazon_order_id
        for o in client.orders_v0.iter_list_orders(
            marketplace_ids=["ATVPDKIKX0DER"], created_after="2020-01-01T00:00:00Z", max_results_per_page=1
        )
    ]
    assert ids == ["902-1", "902-2", "902-3"]
    urls = [str(r.url) for r in mock.by_path("/orders/v0/orders")]
    assert set(urls[0].split("?")[1].split("&")) == {
        "MarketplaceIds=ATVPDKIKX0DER",
        "CreatedAfter=2020-01-01T00%3A00%3A00Z",
        "MaxResultsPerPage=1",
    }
    assert urls[1].endswith("/orders/v0/orders?NextToken=n2") and urls[2].endswith("?NextToken=n3")  # drop_params_on_next
    assert len(acquires) == 3  # one bucket acquire per page

    async def go() -> list[str]:
        aclient = asp(AmazonMock())
        return [
            o.amazon_order_id
            async for o in aclient.orders_v0.iter_list_orders(marketplace_ids=["ATVPDKIKX0DER"], created_after="2020-01-01T00:00:00Z")
        ]

    assert asyncio.run(go()) == ["902-1", "902-2", "902-3"]


def test_raw_mode_and_request_id() -> None:
    mock = AmazonMock()
    client = sp(mock)
    raw = client.orders_v0.list_orders(
        marketplace_ids=["ATVPDKIKX0DER"], created_after="2020-01-01T00:00:00Z", request_options=RequestOptions(raw=True)
    )
    assert raw["payload"]["Orders"][0]["AmazonOrderId"] == "902-1"
    orders = client.orders_v0.iter_list_orders(
        marketplace_ids=["ATVPDKIKX0DER"], created_after="2020-01-01T00:00:00Z", request_options=RequestOptions(raw=True)
    )
    assert [o["AmazonOrderId"] for o in orders] == ["902-1", "902-2", "902-3"]
    with pytest.raises(Exception) as ei:
        client.orders_v0.list_order_order_items(order_id="missing")
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
    models = n = client.notifications_models
    assert "OrderChangeNotification" in models.names
    schema_dir = default_schema_dir() / "notifications"
    assert set(models.names) == {p.stem for p in schema_dir.glob("*.json")}
    payload = json.loads((schema_dir / "OrderChangeNotification.json").read_text())["examples"][0]
    parsed = models.parse(json.dumps(payload).encode())
    assert type(parsed).__name__ == "OrderChangeNotification"
    assert parsed.payload.order_change_notification.amazon_order_id == payload["Payload"]["OrderChangeNotification"]["AmazonOrderId"]
    assert models.model("ListingsItemIssuesChangeNotification_2023-12-13").__name__ == "ListingsItemIssuesChangeNotification_2023_12_13"
    # Known irregularities in the pinned schemas:
    # - ListingsItemStatusChangeNotification.json's own example says LISTINGS_ITEM_STATUS_CHANGE
    #   while the schema enum says LISTINGS_ITEM_STATUS_CHANGED
    # - ShipmentTrackingMilestoneChangedNotification.json is a dangling "$ref": "#/definitions/Notification";
    #   the generator turns it into an empty (extra="allow") model, so its example validates
    # - B2bAnyOfferChangedNotification.json spells its root reference "#ref"; the generator repairs it
    known_bad = {"ListingsItemStatusChangeNotification"}
    assert n.model("ShipmentTrackingMilestoneChangedNotification").model_fields == {}
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
    docs = load_documents()
    orders = raw_operations(docs[("orders", "v0")])
    examples = sandbox_examples(orders["getOrders"])
    assert examples and examples[0].status == 200 and examples[0].parameters["MarketplaceIds"] == ["ATVPDKIKX0DER"]
    assert any(e.status == 400 for e in examples)
    assert sandbox_examples(orders["confirmShipment"])[0].has_body
    assert is_dynamic_sandbox(raw_operations(docs[("shipping", "v2")])["getRates"])
    sources = {e.source for raw in raw_operations(docs[("vendor_shipments", "v1")]).values() for e in sandbox_examples(raw)}
    assert "x-amazon-spds-sandbox-behaviors" in sources


@pytest.mark.parametrize("api", ["orders", "listings_items"])
def test_sandbox_runner(api: str) -> None:
    from . import sandbox

    def sync_factory(transport: httpx2.MockTransport | None) -> Any:
        return SellingPartner(transport=transport, sandbox=True, throttle=False, max_retries=0, credentials=None)

    def async_factory(transport: httpx2.MockTransport | None) -> Any:
        return AsyncSellingPartner(transport=transport, sandbox=True, throttle=False, max_retries=0, credentials=None)

    outcomes = sandbox.run(sync_factory, async_factory, [api])
    failures = [f"{o.mode} {o.case.module}.{o.case.operation_id}[{o.case.status}]: {o.error}" for o in outcomes if not o.ok]
    ops = {o.case.operation_id for o in outcomes}
    expected = {op_id for (a, _v), doc in load_documents().items() if a == api for op_id in raw_operations(doc)}
    assert ops == expected
    assert not failures, "\n".join(failures)


def test_default_spec_dir_exists() -> None:
    assert default_spec_dir().is_dir()
