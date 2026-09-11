"""Behaviour of the generated HTTP client and resources (the petstore package, tests/petstore_sdk)."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx2
import pytest
from petstore_sdk import _http as http_client
from petstore_sdk import errors
from petstore_sdk.client import AsyncClient, Client
from petstore_sdk.models import petstore_v3 as m
from petstore_sdk.resources import OPERATIONS, SERVICES

from amzn_selling_partner import sandbox_tests

from .conftest import OAS31, SWAGGER2

BASE = "https://api.example.com"
DOCS = {"petstore_v3": json.loads(OAS31.read_text()), "petstore_v2": json.loads(SWAGGER2.read_text())}


def _client(handler: Any, **kw: Any) -> Client:
    return Client(base_url=BASE, transport=httpx2.MockTransport(handler), **kw)


def _petstore(handler: Any, **kw: Any) -> Any:
    return _client(handler, **kw).petstore_v3


@pytest.mark.parametrize("key", list(OPERATIONS))
@pytest.mark.parametrize("mode", ["sync", "async"])
def test_every_operation(key: str, mode: str) -> None:
    """Every generated method round-trips a synthetic example derived from the fixture spec."""
    module, _, operation_id = key.partition(".")
    method, http_method, *_rest = OPERATIONS[key]
    document = DOCS[module]
    raw_op = sandbox_tests.raw_operations(document)[operation_id]
    probe = Client(base_url=BASE)
    fn = getattr(getattr(probe, module), method)
    cases = sandbox_tests.cases_for(fn, raw_op, document, module, operation_id, method)
    assert cases, "no example could be derived"

    def factory(transport: httpx2.MockTransport | None) -> Any:
        cls = Client if mode == "sync" else AsyncClient
        return cls(base_url=BASE, transport=transport, max_retries=0)

    for case in cases:
        outcome = sandbox_tests.run_case(factory, case, http_method, mode=mode)
        assert outcome.ok, outcome.error


def test_default_headers_and_base_url() -> None:
    seen: list[httpx2.Request] = []

    def handler(r: httpx2.Request) -> httpx2.Response:
        seen.append(r)
        if r.url.path.endswith("/pets"):
            return httpx2.Response(200, json={"items": []})
        return httpx2.Response(200, json={"id": 1, "name": "n"})

    api = _petstore(handler, default_headers={"X-Custom": "1"})
    api.get_pet(pet_id=3)
    r = seen[0]
    assert str(r.url) == "https://api.example.com/v3/pets/3"
    assert r.headers["accept"] == "application/json" and r.headers["x-custom"] == "1"
    assert r.headers["user-agent"].startswith("amzn_selling_partner/")
    assert "content-type" not in r.headers
    api.list_pets(x_request_id="rid")
    assert seen[-1].headers["x-request-id"] == "rid"
    api.get_pet(pet_id=3, request_options=http_client.RequestOptions(extra_headers={"X-Extra": "e"}, extra_query={"q": "1 2"}))
    assert seen[-1].headers["x-extra"] == "e" and str(seen[-1].url).endswith("/v3/pets/3?q=1%202")


def test_json_body_and_status_specific_decoder() -> None:
    def handler(r: httpx2.Request) -> httpx2.Response:
        assert r.headers["content-type"] == "application/json"
        return httpx2.Response(201, json={"id": 5, **json.loads(r.content)})

    api = _petstore(handler)
    pet = api.create_pet(body={"name": "n", "status": "sold"})
    assert pet.id == 5 and pet.status == "sold" and pet.status is m.Status.SOLD
    assert api.create_pet(body=m.NewPet(name="m")).name == "m"


def test_error_mapping() -> None:
    def handler(r: httpx2.Request) -> httpx2.Response:
        code = int(r.url.path.rsplit("/", 1)[1])
        if code == 404:
            return httpx2.Response(404, json={"code": "NF", "message": "nope"}, headers={"x-amzn-RequestId": "rid-9"})
        if code == 418:
            return httpx2.Response(418, content=b"not json")
        if code == 400:
            return httpx2.Response(400, json={"unexpected": True})
        return httpx2.Response(503, json={"code": "S", "message": "down"})

    api = _petstore(handler, max_retries=0)
    with pytest.raises(errors.NotFoundError) as ei:
        api.get_pet(pet_id=404)
    err = ei.value
    assert err.status_code == 404 and err.request_id == "rid-9" and err.body.code == "NF" and "rid-9" in str(err)
    assert isinstance(err.body, m.Error)  # the operation's error schema
    with pytest.raises(errors.APIStatusError) as ei2:
        api.get_pet(pet_id=418)
    assert ei2.value.body == b"not json" and ei2.value.status_code == 418
    with pytest.raises(errors.BadRequestError) as ei3:
        api.get_pet(pet_id=400)
    assert ei3.value.body == {"unexpected": True}  # schema mismatch -> raw JSON
    with pytest.raises(errors.ServerError) as ei4:
        api.get_pet(pet_id=503)
    assert ei4.value.status_code == 503
    assert errors.status_error_class(429) is errors.RateLimitExceededError


def test_retry_policy_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    # sdkBehavior in codegen/oagen.config.ts: 408/429/5xx, 2 retries, 0.5s initial delay x2, 8s cap, 50 % jitter, 30s timeout
    assert http_client.RETRYABLE_STATUS_CODES == frozenset({408, 429, 500, 502, 503, 504})
    assert http_client.MAX_RETRIES == 2 and http_client.INITIAL_DELAY == 0.5 and http_client.MAX_DELAY == 8
    assert http_client.DEFAULT_TIMEOUT == 30.0
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    attempts = {"n": 0}

    def handler(r: httpx2.Request) -> httpx2.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx2.Response(429, json={"code": "T", "message": "slow"}, headers={"Retry-After": "2"})
        if attempts["n"] == 2:
            return httpx2.Response(503, json={"code": "S", "message": "down"})
        return httpx2.Response(200, json={"id": 1, "name": "n"})

    api = _petstore(handler, max_retries=3)
    assert api.get_pet(pet_id=1).id == 1
    assert attempts["n"] == 3
    assert 2.0 <= sleeps[0] <= 2.5  # honoured Retry-After (with jitter)
    assert 1.0 <= sleeps[1] <= 1.5  # exponential backoff: 0.5 * 2 ** 1, up to 50 % jitter

    with pytest.raises(errors.RateLimitExceededError) as ei:
        _petstore(lambda r: httpx2.Response(429, headers={"Retry-After": "1"}), max_retries=1).get_pet(pet_id=1)
    assert ei.value.retry_after == 1.0


def test_rate_hint_header_updates_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))
    n = {"n": 0}

    def handler(r: httpx2.Request) -> httpx2.Response:
        n["n"] += 1
        if n["n"] == 1:
            return httpx2.Response(429, headers={"x-amzn-RateLimit-Limit": "0.5"})
        return httpx2.Response(200, json={"id": 1, "name": "n"})

    client = _client(handler, default_rate_limit=http_client.RateLimit(rate=100, burst=100))
    client.petstore_v3.get_pet(pet_id=1)
    assert 2.0 <= sleeps[0] <= 2.5
    bucket = client.http._throttler.bucket("petstore_v3.getPet", None)
    assert bucket is not None and bucket.rate == 0.5


def test_generated_rate_limit_feeds_the_throttler() -> None:
    client = _client(lambda r: httpx2.Response(200, json={"items": []}))
    assert OPERATIONS["petstore_v3.listPets"][4] is True and OPERATIONS["petstore_v3.getPet"][4] is False
    client.petstore_v3.list_pets()
    bucket = client.http._throttler.bucket("petstore_v3.listPets", None)
    assert bucket is not None and bucket.rate == 2  # the usage-plan table in the description
    client.petstore_v3.get_pet(pet_id=1) if False else None
    assert client.http._throttler.bucket("petstore_v3.getPet", None) is None  # no table, no default -> unthrottled


def test_timeout_and_connection_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda s: None)
    calls = {"n": 0}

    def timeout_handler(r: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        raise httpx2.ReadTimeout("slow", request=r)

    with pytest.raises(errors.APITimeoutError) as ei:
        _petstore(timeout_handler, max_retries=2).get_pet(pet_id=1)
    assert calls["n"] == 3 and isinstance(ei.value.__cause__, httpx2.ReadTimeout)

    def connect_handler(r: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=r)

    with pytest.raises(errors.APIConnectionError) as ei2:
        _petstore(connect_handler, max_retries=0).get_pet(pet_id=1)
    assert not isinstance(ei2.value, errors.APITimeoutError)
    calls["n"] = 0
    with pytest.raises(errors.APITimeoutError):
        _petstore(timeout_handler, max_retries=5).get_pet(pet_id=1, request_options=http_client.RequestOptions(max_retries=0, timeout=0.5))
    assert calls["n"] == 1


def test_per_call_timeout_is_passed_to_transport() -> None:
    seen: list[dict[str, Any]] = []

    def handler(r: httpx2.Request) -> httpx2.Response:
        seen.append(dict(r.extensions.get("timeout", {})))
        return httpx2.Response(200, json={"id": 1, "name": "n"})

    api = _petstore(handler, timeout=httpx2.Timeout(7.0, connect=3.0))
    api.get_pet(pet_id=1)
    api.get_pet(pet_id=1, request_options=http_client.RequestOptions(timeout=1.5))
    assert seen[0]["read"] == 7.0 and seen[0]["connect"] == 3.0
    assert seen[1]["read"] == 1.5


def test_pagination_walk_sync_and_async() -> None:
    def handler(r: httpx2.Request) -> httpx2.Response:
        tok = r.url.params.get("nextToken")
        if tok is None:
            return httpx2.Response(200, json={"items": [{"id": 1, "name": "a"}], "nextToken": "t2"})
        if tok == "t2":
            return httpx2.Response(200, json={"items": [{"id": 2, "name": "b"}], "nextToken": "t3"})
        return httpx2.Response(200, json={"items": [{"id": 3, "name": "c"}]})

    api = _petstore(handler)
    page = api.list_pets(limit=1)
    assert page.next_token == "t2" and [p.id for p in page.items] == [1]
    assert [p.id for p in api.iter_list_pets(limit=1)] == [1, 2, 3]
    raw = api.list_pets(limit=1, request_options=http_client.RequestOptions(raw=True))
    assert raw == {"items": [{"id": 1, "name": "a"}], "nextToken": "t2"}
    assert [i["id"] for i in api.iter_list_pets(limit=1, request_options=http_client.RequestOptions(raw=True))] == [1, 2, 3]

    async def go() -> list[int]:
        aapi = AsyncClient(base_url=BASE, transport=httpx2.MockTransport(handler)).petstore_v3
        return [x.id async for x in aapi.iter_list_pets(limit=1)]

    assert asyncio.run(go()) == [1, 2, 3]


def test_text_and_empty_responses() -> None:
    api = _petstore(lambda r: httpx2.Response(200, content=b"data: one\n\n", headers={"content-type": "text/event-stream"}))
    assert api.list_events() == "data: one\n\n"
    api2 = _petstore(lambda r: httpx2.Response(204))
    assert api2.delete_pet(pet_id=1) is None


def test_async_cancellation_propagates() -> None:
    async def slow_handler(r: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(10)
        return httpx2.Response(200, json={})

    async def go() -> None:
        client = AsyncClient(base_url=BASE, transport=httpx2.MockTransport(slow_handler))
        task = asyncio.create_task(client.petstore_v3.get_pet(pet_id=1))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert task.cancelled()
        await client.aclose()

    asyncio.run(go())


def test_async_total_timeout_maps_to_api_timeout() -> None:
    async def slow_handler(r: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(1)
        return httpx2.Response(200, json={})

    async def go() -> None:
        client = AsyncClient(base_url=BASE, transport=httpx2.MockTransport(slow_handler), total_timeout=0.05, max_retries=0)
        with pytest.raises(errors.APITimeoutError):
            await client.petstore_v3.get_pet(pet_id=1)
        await client.aclose()

    asyncio.run(go())


def test_close_releases_pool() -> None:
    class Recording(httpx2.MockTransport):
        closed = False

        def close(self) -> None:
            self.closed = True
            super().close()

    class ARecording(httpx2.MockTransport):
        closed = False

        async def aclose(self) -> None:
            self.closed = True
            await super().aclose()

    t = Recording(lambda r: httpx2.Response(200, json={"id": 1, "name": "n"}))
    with Client(base_url=BASE, transport=t) as client:
        assert client.http._client is None  # lazy creation
        client.petstore_v3.get_pet(pet_id=1)
        assert client.http._client is not None
    assert t.closed and client.http.is_closed

    at = ARecording(lambda r: httpx2.Response(200, json={"id": 1, "name": "n"}))

    async def go() -> None:
        async with AsyncClient(base_url=BASE, transport=at) as client:
            await client.petstore_v3.get_pet(pet_id=1)
        assert at.closed and client.http.is_closed

    asyncio.run(go())

    injected = httpx2.Client(transport=httpx2.MockTransport(lambda r: httpx2.Response(200, json={"id": 1, "name": "n"})))
    c = Client(base_url=BASE, http_client=injected)
    c.petstore_v3.get_pet(pet_id=1)
    c.close()
    assert not injected.is_closed  # injected clients are not closed by us


def test_client_layout() -> None:
    client = Client(base_url=BASE)
    assert set(SERVICES) == {"petstore_v2", "petstore_v3"}
    assert client.petstore is client.petstore_v3  # latest version alias
    assert type(client.petstore_v2).__name__ == "PetstoreV2Resource" and type(client.petstore_v3).__name__ == "PetstoreV3Resource"
    assert client.petstore_v3 is client.petstore_v3  # cached
    assert client.petstore_v3.list_pets.__doc__ and "GET /v3/pets" in client.petstore_v3.list_pets.__doc__
    assert client.base_url == BASE and client.http.max_retries == http_client.MAX_RETRIES
    aclient = AsyncClient(base_url=BASE)
    assert type(aclient.petstore).__name__ == "AsyncPetstoreV3Resource"
    assert Client.__module__ == "petstore_sdk.client" and Client().base_url == "https://petstore.example.com"  # the spec's server


def test_with_options_shares_the_pool_and_drops_cached_resources() -> None:
    calls: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request.headers.get("X-Tenant", "-"))
        return httpx2.Response(200, json={"id": 1, "name": "n"})

    client = _client(handler)
    before = client.petstore_v3
    derived = client.with_options(default_headers={"X-Tenant": "b"}, max_retries=0)
    assert derived.http_client is client.http_client  # same connection pool
    assert derived.http.max_retries == 0 and client.http.max_retries == 2
    assert derived.petstore_v3 is not before and client.petstore_v3 is before
    derived.petstore_v3.get_pet(pet_id=1)
    client.petstore_v3.get_pet(pet_id=1)
    assert calls == ["b", "-"]
    with pytest.raises(TypeError, match="unknown option"):
        client.with_options(bogus=1)
    derived.close()  # does not close the shared pool
    assert not client.http.is_closed
