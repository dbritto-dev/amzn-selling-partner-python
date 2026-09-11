"""Runtime client behaviour over the generated petstore package (tests/petstore_sdk)."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from typing import Any

import httpx2
import pytest
from petstore_sdk.client import AsyncClient, Client
from petstore_sdk.resources.petstore.v2 import PetstoreV2
from petstore_sdk.resources.petstore.v3 import PetstoreV3

from amzn_selling_partner import APIConnectionError, APIStatusError, APITimeoutError, NotFoundError, RateLimitError, RequestOptions
from amzn_selling_partner._examples import example_from_schema
from amzn_selling_partner.runtime import NOT_GIVEN, Pagination, RateLimit
from amzn_selling_partner.runtime._op import Op
from amzn_selling_partner.runtime._serializers import scalar
from amzn_selling_partner.runtime._stream import AsyncStream, Stream
from amzn_selling_partner.sandbox_tests import raw_operations

from .conftest import OAS31, SWAGGER2, maybe_await

BASE = "https://api.example.com/v1"
DOCS = {"v3": json.loads(OAS31.read_text()), "v2": json.loads(SWAGGER2.read_text())}
RESOURCES = {"v3": PetstoreV3, "v2": PetstoreV2}


def _all_ops() -> list[tuple[str, str]]:
    return [(version, op.operation_id) for version, cls in RESOURCES.items() for op in cls._ops.values()]


def _raw_op(version: str, operation_id: str) -> dict[str, Any]:
    return raw_operations(DOCS[version])[operation_id]


def _example_kwargs(version: str, op: Op) -> dict[str, Any]:
    doc = DOCS[version]
    raw = _raw_op(version, op.operation_id)
    params = {p["name"]: p for p in raw["parameters"]}
    kwargs: dict[str, Any] = {}
    for p in op.params:
        if p.required:
            spec = params[p.wire_name]
            schema = spec.get("schema") or {k: v for k, v in spec.items() if k in ("type", "items", "format", "enum")}
            kwargs[p.py_name] = example_from_schema(doc, schema)
    if op.body is not None and op.body.required:
        if op.body.kind == "json":
            body_param = next((p for p in raw["parameters"] if p.get("in") == "body"), None)
            schema = body_param["schema"] if body_param else raw["requestBody"]["content"]["application/json"]["schema"]
            kwargs["body"] = example_from_schema(doc, schema)
        elif op.body.kind in ("multipart", "form"):
            kwargs["body"] = b"raw"
        else:
            kwargs["body"] = b"\x00\x01"
    return kwargs


def _success_response(version: str, op: Op) -> httpx2.Response:
    doc = DOCS[version]
    raw = _raw_op(version, op.operation_id)
    for code, resp in raw["responses"].items():
        if code.startswith("2"):
            status = int(code)
            content = resp.get("content") or {}
            schema = resp.get("schema") or next((m.get("schema") for m in content.values() if m.get("schema")), None)
            media = next(iter(content), None) or (raw.get("produces") or doc.get("produces") or ["application/json"])[0]
            if media == "text/event-stream":
                return httpx2.Response(status, content=b'event: ping\ndata: {"a":1}\n\n', headers={"content-type": media})
            if schema is not None:
                return httpx2.Response(status, json=example_from_schema(doc, schema, all_fields=True))
            if not content and "produces" not in raw and status == 204:
                return httpx2.Response(status)
            if media.startswith("text/"):
                return httpx2.Response(status, content=b"plain text", headers={"content-type": media})
            return httpx2.Response(status)
    raise AssertionError("no success response")


@pytest.mark.parametrize(("version", "operation_id"), _all_ops())
@pytest.mark.parametrize("mode", ["sync", "async"])
def test_every_operation(version: str, operation_id: str, mode: str) -> None:
    op = next(o for o in RESOURCES[version]._ops.values() if o.operation_id == operation_id)
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return _success_response(version, op)

    cls = Client if mode == "sync" else AsyncClient
    client = cls(base_url=BASE, transport=httpx2.MockTransport(handler), max_retries=0)
    api = client.petstore.version(version)
    method = getattr(api, op.name)
    kwargs = _example_kwargs(version, op)

    async def go() -> Any:
        result = await maybe_await(method(**kwargs))
        if isinstance(result, (Stream, AsyncStream)):
            events = [e async for e in result.iter_events()] if mode == "async" else list(result.iter_events())
            assert events and events[0].event == "ping" and events[0].json() == {"a": 1}
            await maybe_await(result.aclose() if mode == "async" else result.close())
        raw = await maybe_await(method(**kwargs, raw=True))
        return result, raw

    result, raw = asyncio.run(go())
    request = seen[0]
    assert request.method == op.method
    assert request.url.path.startswith("/v1")
    for p in op.path_params:
        assert scalar(kwargs[p.py_name]) in request.url.path
    if op.body is not None and op.body.required:
        assert request.content
    if op.default_decoder.kind == "json":
        if op.compiled_pagination is not None:
            assert hasattr(result, "items")
            assert isinstance(raw.raw, dict)
        else:
            assert result is not None
            assert isinstance(raw, (dict, list))
    elif op.default_decoder.kind == "none" and not op.stream_default:
        assert result is None and raw is None
    asyncio.run(maybe_await(client.aclose() if mode == "async" else client.close()))


def _petstore(handler: Any, **kw: Any) -> PetstoreV3:
    return Client(base_url=BASE, transport=httpx2.MockTransport(handler), backoff_initial=0.0001, **kw).petstore.latest


def test_default_headers_and_base_url() -> None:
    seen: list[httpx2.Request] = []

    def handler(r: httpx2.Request) -> httpx2.Response:
        seen.append(r)
        if r.url.path.endswith("/pets"):
            return httpx2.Response(200, json={"items": []})
        return httpx2.Response(200, json={"id": 1, "name": "n"})

    api = _petstore(handler, headers={"X-Custom": "1"})
    api.get_pet(pet_id=3)
    r = seen[0]
    assert str(r.url) == "https://api.example.com/v1/pets/3"
    assert r.headers["accept"] == "application/json" and r.headers["x-custom"] == "1"
    assert r.headers["user-agent"].startswith("amzn_selling_partner/")
    assert "content-type" not in r.headers
    api.list_pets(x_request_id="rid")
    assert seen[-1].headers["x-request-id"] == "rid"
    api.get_pet(pet_id=3, request_options=RequestOptions(extra_headers={"X-Extra": "e"}, extra_query={"q": "1 2"}))
    assert seen[-1].headers["x-extra"] == "e" and str(seen[-1].url).endswith("/pets/3?q=1%202")


def test_json_body_and_status_specific_decoder() -> None:
    def handler(r: httpx2.Request) -> httpx2.Response:
        assert r.headers["content-type"] == "application/json"
        return httpx2.Response(201, json={"id": 5, **json.loads(r.content)})

    api = _petstore(handler)
    pet = api.create_pet(body={"name": "n", "status": "sold"})
    assert pet.id == 5 and pet.status == "sold"
    assert api.create_pet(body=api.models.NewPet(name="m")).name == "m"


def test_error_mapping() -> None:
    def handler(r: httpx2.Request) -> httpx2.Response:
        code = int(r.url.path.rsplit("/", 1)[1])
        if code == 404:
            return httpx2.Response(404, json={"code": "NF", "message": "nope"}, headers={"x-request-id": "rid-9"})
        if code == 418:
            return httpx2.Response(418, content=b"not json")
        if code == 400:
            return httpx2.Response(400, json={"unexpected": True})
        return httpx2.Response(503, json={"code": "S", "message": "down"})

    api = _petstore(handler, max_retries=0)
    with pytest.raises(NotFoundError) as ei:
        api.get_pet(pet_id=404)
    err = ei.value
    assert err.status_code == 404 and err.request_id == "rid-9" and err.body.code == "NF" and "rid-9" in str(err)
    with pytest.raises(APIStatusError) as ei2:
        api.get_pet(pet_id=418)
    assert ei2.value.body == b"not json" and ei2.value.status_code == 418
    with pytest.raises(APIStatusError) as ei3:
        api.get_pet(pet_id=400)
    assert ei3.value.body == {"unexpected": True}  # schema mismatch -> raw JSON
    with pytest.raises(APIStatusError) as ei4:
        api.get_pet(pet_id=503)
    assert ei4.value.status_code == 503


def test_retry_on_429_and_5xx_with_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert sleeps[1] < 1.0  # exponential backoff

    with pytest.raises(RateLimitError) as ei:
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

    client = Client(
        base_url=BASE,
        transport=httpx2.MockTransport(handler),
        rate_hint_header="x-amzn-RateLimit-Limit",
        default_rate_limit=RateLimit(rate=100, burst=100),
    )
    client.petstore.latest.get_pet(pet_id=1)
    assert 2.0 <= sleeps[0] <= 2.5
    assert client._throttler is not None
    bucket = client._throttler.bucket("petstore.v3.getPet", None)
    assert bucket is not None and bucket.rate == 0.5


def test_generated_rate_limit_feeds_the_throttler() -> None:
    client = Client(base_url=BASE, transport=httpx2.MockTransport(lambda r: httpx2.Response(200, json={"items": []})))
    op = client.petstore.v3.operation("listPets")
    assert op.rate_limit is None  # rate-limit tables are an Amazon policy; the generic emitter leaves them out
    client.petstore.v3.list_pets()
    assert client._throttler is not None and client._throttler.bucket(op.key, op.rate_limit) is None


def test_timeout_and_connection_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda s: None)
    calls = {"n": 0}

    def timeout_handler(r: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        raise httpx2.ReadTimeout("slow", request=r)

    with pytest.raises(APITimeoutError) as ei:
        _petstore(timeout_handler, max_retries=2).get_pet(pet_id=1)
    assert calls["n"] == 3 and isinstance(ei.value.__cause__, httpx2.ReadTimeout)

    def connect_handler(r: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=r)

    with pytest.raises(APIConnectionError) as ei2:
        _petstore(connect_handler, max_retries=0).get_pet(pet_id=1)
    assert not isinstance(ei2.value, APITimeoutError)
    with pytest.raises(APITimeoutError):
        _petstore(timeout_handler, max_retries=5).get_pet(pet_id=1, request_options=RequestOptions(max_retries=0, timeout=0.5))


def test_per_call_timeout_is_passed_to_transport() -> None:
    seen: list[dict[str, Any]] = []

    def handler(r: httpx2.Request) -> httpx2.Response:
        seen.append(dict(r.extensions.get("timeout", {})))
        return httpx2.Response(200, json={"id": 1, "name": "n"})

    api = _petstore(handler, timeout=httpx2.Timeout(7.0, connect=3.0))
    api.get_pet(pet_id=1)
    api.get_pet(pet_id=1, request_options=RequestOptions(timeout=1.5))
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
    assert page.has_next and page.next_token == "t2" and [p.id for p in page.items] == [1]
    assert [p.id for p in page] == [1, 2, 3]
    assert [len(p.items) for p in page.pages()] == [1, 1, 1]
    assert [p.id for p in page.all()] == [1, 2, 3]
    assert page.next_page().next_page().next_page() is None  # type: ignore[union-attr]
    raw: Any = api.list_pets(limit=1, raw=True)
    assert raw.items == [{"id": 1, "name": "a"}] and [i["id"] for i in raw] == [1, 2, 3]
    plain: Any = api.list_pets(limit=1, paginate=None)
    assert plain.items[0].id == 1 and not hasattr(plain, "next_page")

    async def go() -> list[int]:
        aapi = AsyncClient(base_url=BASE, transport=httpx2.MockTransport(handler)).petstore.latest
        p = await aapi.list_pets(limit=1)
        ids = [x.id async for x in p]
        pages = [len(pg.items) async for pg in p.pages()]
        assert pages == [1, 1, 1] and (await p.all())[0].id == 1
        return ids

    assert asyncio.run(go()) == [1, 2, 3]


def test_pagination_override_per_call_and_drop_params() -> None:
    seen: list[str] = []

    def handler(r: httpx2.Request) -> httpx2.Response:
        seen.append(str(r.url))
        tok = r.url.params.get("nextToken")
        if tok is None:
            return httpx2.Response(200, json={"events": ["a"], "warnings": ["w"], "nextToken": "n2"})
        return httpx2.Response(200, json={"events": ["b"], "warnings": []})

    api = _petstore(handler)
    assert not hasattr(api.list_audit(), "next_page")  # model, not page (ambiguous detection)
    page: Any = api.list_audit(
        paginate=Pagination(items_path="events", next_token_path="nextToken", next_token_param="nextToken", drop_params_on_next=True)
    )
    assert list(page) == ["a", "b"]
    assert seen[-1].endswith("/audit?nextToken=n2")


def test_async_cancellation_propagates() -> None:
    async def slow_handler(r: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(10)
        return httpx2.Response(200, json={})

    async def go() -> None:
        client = AsyncClient(base_url=BASE, transport=httpx2.MockTransport(slow_handler))
        api = client.petstore.latest
        task = asyncio.create_task(api.get_pet(pet_id=1))
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
        with pytest.raises(APITimeoutError):
            await client.petstore.latest.get_pet(pet_id=1)
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
        assert client._client is None  # lazy creation
        client.petstore.latest.get_pet(pet_id=1)
        assert client._client is not None
    assert t.closed and client.is_closed

    at = ARecording(lambda r: httpx2.Response(200, json={"id": 1, "name": "n"}))

    async def go() -> None:
        async with AsyncClient(base_url=BASE, transport=at) as client:
            await client.petstore.latest.get_pet(pet_id=1)
        assert at.closed and client.is_closed

    asyncio.run(go())

    injected = httpx2.Client(transport=httpx2.MockTransport(lambda r: httpx2.Response(200, json={"id": 1, "name": "n"})))
    c = Client(base_url=BASE, http_client=injected)
    c.petstore.latest.get_pet(pet_id=1)
    c.close()
    assert not injected.is_closed  # injected clients are not closed by us


def test_streaming_sse_and_bytes() -> None:
    body = b'data: one\n\nevent: two\ndata: {"x": 2}\nid: 7\n\n: comment\r\n\r\ndata: three\r\ndata: more\r\n\r\n'
    api = _petstore(lambda r: httpx2.Response(200, content=body, headers={"content-type": "text/event-stream"}))
    with api.stream_events() as stream:
        events = list(stream.iter_events())
    assert [(e.event, e.data, e.id) for e in events] == [(None, "one", None), ("two", '{"x": 2}', "7"), (None, "three\nmore", None)]
    assert events[1].json() == {"x": 2}
    with api.stream_events() as stream:
        assert b"".join(stream.iter_bytes()) == body

    async def go() -> None:
        aapi = AsyncClient(base_url=BASE, transport=httpx2.MockTransport(lambda r: httpx2.Response(200, content=body))).petstore.latest
        async with await aapi.stream_events() as stream:
            evs = [e.data async for e in stream.iter_events()]
        assert evs == ["one", '{"x": 2}', "three\nmore"]

    asyncio.run(go())


def test_stream_error_raises_status_error() -> None:
    api = _petstore(lambda r: httpx2.Response(500, json={"code": "E", "message": "boom"}), max_retries=0)
    with pytest.raises(APIStatusError) as ei:
        api.stream_events()
    assert ei.value.body == {"code": "E", "message": "boom"}  # no error schema declared -> raw JSON


def test_dir_and_introspection() -> None:
    client = Client(base_url=BASE, transport=httpx2.MockTransport(lambda r: httpx2.Response(500)))
    assert "petstore" in dir(client) and client.apis == ["petstore"] and client.aliases == {"pets": "petstore"}
    versions = client.petstore
    assert versions.versions == ["v2", "v3"] and "latest" in dir(versions) and versions.api == "petstore"
    assert client.pets is versions and client.api("pets") is versions and versions.latest is versions.v3
    api = versions.latest
    assert "list_pets" in dir(api) and api.models.__name__ == "petstore_sdk.models.petstore.v3"
    assert api.operation("listPets").name == "list_pets" and api.operation("list_pets").operation_id == "listPets"
    assert api.list_pets.__doc__ and "GET /pets" in api.list_pets.__doc__
    assert list(api) == list(api.operations) and repr(api).startswith("<PetstoreV3 petstore.v3: ")
    with pytest.raises(AttributeError, match="no API named"):
        client.api("nope")
    with pytest.raises(AttributeError, match="no version"):
        _ = versions.v9
    with pytest.raises(KeyError):
        api.operation("nope")


def test_preload_reports_times() -> None:
    client = Client(base_url=BASE, transport=httpx2.MockTransport(lambda r: httpx2.Response(500)))
    times = client.preload()
    assert set(times) == {"petstore.v2", "petstore.v3"}
    assert all(t >= 0 for t in times.values())
    assert client.api_versions() == {"petstore": ["v2", "v3"]}


def test_not_given_import_and_repr() -> None:
    assert repr(NOT_GIVEN) == "NOT_GIVEN" and not NOT_GIVEN
    assert inspect.signature(PetstoreV3.list_pets).parameters["limit"].default is NOT_GIVEN
