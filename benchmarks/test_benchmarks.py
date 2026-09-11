"""pytest-benchmark suite: the generated call path against hand-written httpx2 code.

    uv run pytest benchmarks                       # run (also asserts the 10 % ratio)
    uv run pytest benchmarks --benchmark-disable   # just exercise the scenarios once
    uv run pytest benchmarks --benchmark-save=main # keep a baseline (.benchmarks/, git-ignored)
    uv run pytest benchmarks --benchmark-compare=0001 --benchmark-compare-fail=min:15%

Requests go through ``httpx2.MockTransport`` (no network, no server) so the
numbers isolate the client overhead: URL building, headers, retries/throttle
bookkeeping, decoding. Groups:

* ``sync``  – transport only / hand-written function / generated method / generated method ``raw=True``
* ``async`` – the same on the async client
* ``decode`` – ``TypeAdapter.validate_json`` (models) vs ``pydantic_core.from_json`` (raw) on 100 KB and 1 MB bodies

The last test asserts that the generated method costs at most 1.10× the
hand-written function (best-of-rounds ``min``), the target from docs/PLAN.md.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import sys
from collections.abc import Callable
from typing import Any

import httpx2
import pytest
from pydantic_core import from_json

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))  # the generated petstore package (codegen/)

from petstore_sdk._http import RequestOptions  # noqa: E402
from petstore_sdk.client import AsyncClient, Client  # noqa: E402
from petstore_sdk.models._base import adapter_for  # noqa: E402
from petstore_sdk.models.petstore_v3 import Pet, PetList  # noqa: E402

BASE = "http://bench.invalid"
PET = b'{"id": 1, "name": "rex", "tag": "dog", "status": "available", "tags": ["a", "b"], "createdAt": "2024-01-01T00:00:00Z"}'
RATIO_LIMIT = 1.10

#: ``group/name`` -> best (min) seconds per call, filled by the benchmarks below
_MIN: dict[str, float] = {}


def _handler(request: httpx2.Request) -> httpx2.Response:
    if request.url.path.endswith("/pets"):
        return httpx2.Response(200, json={"items": [json.loads(PET)], "nextToken": None})
    return httpx2.Response(200, content=PET, headers={"content-type": "application/json"})


async def _ahandler(request: httpx2.Request) -> httpx2.Response:
    return _handler(request)


def _record(benchmark: Any, key: str) -> None:
    stats = getattr(benchmark, "stats", None)
    if stats is not None:  # None with --benchmark-disable
        _MIN[key] = float(stats.stats.min)


def pet_list(size: int) -> bytes:
    """A ``{"items": [...]}`` body of roughly ``size`` bytes."""
    item = json.loads(PET)
    items: list[Any] = []
    n = 0
    while n < size:
        items.append(dict(item, id=len(items)))
        n += len(PET) + 4
    return json.dumps({"items": items, "nextToken": "t"}).encode()


# -- sync ------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sync_client() -> Any:
    client = Client(base_url=BASE, transport=httpx2.MockTransport(_handler), throttle=False, max_retries=0)
    yield client
    client.close()


@pytest.mark.benchmark(group="sync")
def test_sync_transport_only(benchmark: Any, sync_client: Any) -> None:
    http = sync_client.http_client
    benchmark(lambda: http.get(f"{BASE}/v3/pets/1").content)
    _record(benchmark, "sync/transport_only")


@pytest.mark.benchmark(group="sync")
def test_sync_hand_written(benchmark: Any, sync_client: Any) -> None:
    http = sync_client.http_client

    def hand_written(pet_id: int) -> Pet:
        request = http.build_request("GET", f"{BASE}/v3/pets/{pet_id}", headers={"Accept": "application/json"})
        response = http.send(request)
        if response.status_code >= 400:
            raise RuntimeError(response.status_code)
        return Pet.model_validate_json(response.content)

    assert benchmark(lambda: hand_written(1)).id == 1
    _record(benchmark, "sync/hand_written")


@pytest.mark.benchmark(group="sync")
def test_sync_generated_method(benchmark: Any, sync_client: Any) -> None:
    api = sync_client.petstore_v3
    assert benchmark(lambda: api.get_pet(pet_id=1)).id == 1
    _record(benchmark, "sync/generated")


@pytest.mark.benchmark(group="sync")
def test_sync_generated_method_raw(benchmark: Any, sync_client: Any) -> None:
    api = sync_client.petstore_v3
    raw = RequestOptions(raw=True)
    assert benchmark(lambda: api.get_pet(pet_id=1, request_options=raw))["id"] == 1
    _record(benchmark, "sync/generated_raw")


# -- async -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def loop() -> Any:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def async_client(loop: Any) -> Any:
    client = AsyncClient(base_url=BASE, transport=httpx2.MockTransport(_ahandler), throttle=False, max_retries=0)
    yield client
    loop.run_until_complete(client.aclose())


def _run(loop: Any, fn: Callable[[], Any]) -> Callable[[], Any]:
    return lambda: loop.run_until_complete(fn())


@pytest.mark.benchmark(group="async")
def test_async_transport_only(benchmark: Any, loop: Any, async_client: Any) -> None:
    http = async_client.http_client

    async def go() -> bytes:
        return (await http.get(f"{BASE}/v3/pets/1")).content

    benchmark(_run(loop, go))
    _record(benchmark, "async/transport_only")


@pytest.mark.benchmark(group="async")
def test_async_hand_written(benchmark: Any, loop: Any, async_client: Any) -> None:
    http = async_client.http_client

    async def hand_written() -> Pet:
        request = http.build_request("GET", f"{BASE}/v3/pets/1", headers={"Accept": "application/json"})
        response = await http.send(request)
        if response.status_code >= 400:
            raise RuntimeError(response.status_code)
        return Pet.model_validate_json(response.content)

    assert benchmark(_run(loop, hand_written)).id == 1
    _record(benchmark, "async/hand_written")


@pytest.mark.benchmark(group="async")
def test_async_generated_method(benchmark: Any, loop: Any, async_client: Any) -> None:
    api = async_client.petstore_v3
    assert benchmark(_run(loop, lambda: api.get_pet(pet_id=1))).id == 1
    _record(benchmark, "async/generated")


# -- decode ----------------------------------------------------------------------------


@pytest.mark.benchmark(group="decode")
@pytest.mark.parametrize("size", [100_000, 1_000_000], ids=["100KB", "1MB"])
def test_decode_models(benchmark: Any, sync_client: Any, size: int) -> None:
    adapter = adapter_for(PetList)
    body = pet_list(size)
    benchmark.extra_info["bytes"] = len(body)
    assert benchmark(lambda: adapter.validate_json(body)).items


@pytest.mark.benchmark(group="decode")
@pytest.mark.parametrize("size", [100_000, 1_000_000], ids=["100KB", "1MB"])
def test_decode_raw(benchmark: Any, size: int) -> None:
    body = pet_list(size)
    benchmark.extra_info["bytes"] = len(body)
    assert benchmark(lambda: from_json(body))["items"]


# -- the target ------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_generated_method_within_10pct_of_hand_written(mode: str) -> None:
    if f"{mode}/generated" not in _MIN:
        pytest.skip("benchmarks disabled")
    ratio = _MIN[f"{mode}/generated"] / _MIN[f"{mode}/hand_written"]
    print(f"{mode}: generated / hand-written = {ratio:.3f} (limit {RATIO_LIMIT})")
    assert ratio <= RATIO_LIMIT, f"{mode}: generated method is {ratio:.3f}x the hand-written function"
