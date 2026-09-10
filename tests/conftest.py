from __future__ import annotations

import asyncio
import inspect
import os
import pathlib
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
OAS31 = FIXTURES / "petstore_oas31.json"
SWAGGER2 = FIXTURES / "petstore_swagger2.json"
AMAZON_MODELS = pathlib.Path(__file__).resolve().parents[1] / "spec/selling-partner-api-models/models"
ORDERS_V0 = AMAZON_MODELS / "orders-api-model/ordersV0.json"
LISTINGS_ITEMS = AMAZON_MODELS / "listings-items-api-model/listingsItems_2021-08-01.json"

requires_amazon = pytest.mark.skipif(not ORDERS_V0.exists(), reason="Amazon models submodule not checked out")


@pytest.fixture(scope="session", autouse=True)
def _ir_cache(tmp_path_factory: pytest.TempPathFactory) -> None:
    os.environ["SPAPI_CACHE_DIR"] = str(tmp_path_factory.mktemp("ir-cache"))


async def maybe_await(value: Any) -> Any:
    """Await coroutines/awaitables, pass everything else through."""
    if inspect.isawaitable(value):
        return await value
    return value


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def mock_transport(handler: Callable[[httpx2.Request], httpx2.Response]) -> httpx2.MockTransport:
    return httpx2.MockTransport(handler)


@pytest.fixture
def maybe_await_fn() -> Callable[[Any], Any]:
    return maybe_await
