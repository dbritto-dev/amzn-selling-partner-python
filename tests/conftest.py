from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

TESTS = pathlib.Path(__file__).parent
FIXTURES = TESTS / "fixtures"
OAS31 = FIXTURES / "petstore_oas31.json"
SWAGGER2 = FIXTURES / "petstore_swagger2.json"
AMAZON_MODELS = TESTS.parents[0] / "spec/selling-partner-api-models/models"
ORDERS_V0 = AMAZON_MODELS / "orders-api-model/ordersV0.json"
LISTINGS_ITEMS = AMAZON_MODELS / "listings-items-api-model/listingsItems_2021-08-01.json"

# the generated petstore test package (codegen/ writes it next to the tests)
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

requires_amazon = pytest.mark.skipif(not ORDERS_V0.exists(), reason="Amazon models submodule not checked out")


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
