"""Generated resource methods (the petstore test package, tests/petstore_sdk): signatures, URL building, bodies, decoding."""

from __future__ import annotations

import datetime
import inspect
import json
from typing import Any

import httpx2
import pytest
from petstore_sdk import errors
from petstore_sdk._http import scalar
from petstore_sdk.client import AsyncClient, Client
from petstore_sdk.models import petstore_v2 as sw2
from petstore_sdk.models import petstore_v3 as models
from petstore_sdk.resources import OPERATIONS, SERVICES
from petstore_sdk.resources.petstore_v2 import AsyncPetstoreV2Resource, PetstoreV2Resource
from petstore_sdk.resources.petstore_v3 import AsyncPetstoreV3Resource, PetstoreV3Resource

BASE = "https://h"


def _methods(cls: type) -> set[str]:
    return {n for n in dir(cls) if not n.startswith("_")}


def test_method_and_param_names() -> None:
    assert _methods(PetstoreV3Resource) == {
        "list_pets",
        "iter_list_pets",
        "create_pet",
        "get_pet",
        "delete_pet",
        "update_pet_photo",
        "list_animals",
        "list_tree",
        "list_audit",
        "list_events",
        "get_label",
    }
    assert {k for k in OPERATIONS if k.startswith("petstore_v3.")} == {
        f"petstore_v3.{op}"
        for op in (
            "listPets",
            "createPet",
            "getPet",
            "deletePet",
            "uploadPhoto",
            "listAnimals",
            "getTree",
            "listAudit",
            "streamEvents",
            "getByLabel",
        )
    }
    assert OPERATIONS["petstore_v3.listPets"] == ("list_pets", "GET", "/v3/pets", True, True)
    assert OPERATIONS["petstore_v2.getReport"][:3] == ("list_report", "GET", "/v2/report")
    assert SERVICES["petstore_v3"] == ("PetstoreV3Resource", "AsyncPetstoreV3Resource")


def test_signature() -> None:
    sig = inspect.signature(PetstoreV3Resource.list_pets)
    params = [p for p in sig.parameters.values() if p.name != "self"]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params)
    assert [p.name for p in params] == ["limit", "tags", "status", "next_token", "x_request_id", "request_options"]
    assert sig.parameters["limit"].default is None and sig.parameters["limit"].annotation == "int | None"
    assert sig.parameters["status"].annotation == "petstore_v3.Status | str | None"
    assert sig.return_annotation == "petstore_v3.PetList"
    assert inspect.signature(PetstoreV3Resource.iter_list_pets).return_annotation == "Iterator[petstore_v3.Pet]"
    assert inspect.signature(AsyncPetstoreV3Resource.iter_list_pets).return_annotation == "AsyncIterator[petstore_v3.Pet]"
    gp = inspect.signature(PetstoreV3Resource.get_pet)
    assert gp.parameters["pet_id"].default is inspect.Parameter.empty and gp.parameters["pet_id"].annotation == "int"
    assert gp.return_annotation == "petstore_v3.Pet"
    assert inspect.signature(PetstoreV3Resource.delete_pet).return_annotation == "None"
    cp = inspect.signature(PetstoreV3Resource.create_pet)
    assert list(cp.parameters)[1] == "body" and cp.parameters["body"].default is inspect.Parameter.empty
    assert cp.parameters["body"].annotation == "petstore_v3.NewPet | Mapping[str, Any]"
    assert inspect.signature(PetstoreV3Resource.update_pet_photo).parameters["body"].annotation == "bytes"
    assert inspect.signature(PetstoreV2Resource.list_report).return_annotation == "str"


def test_sync_async_same_methods_and_signatures() -> None:
    for sync_cls, async_cls in ((PetstoreV3Resource, AsyncPetstoreV3Resource), (PetstoreV2Resource, AsyncPetstoreV2Resource)):
        assert _methods(sync_cls) == _methods(async_cls)
        for name in _methods(sync_cls):
            s, a = getattr(sync_cls, name), getattr(async_cls, name)
            ss, sa = inspect.signature(s), inspect.signature(a)
            assert list(ss.parameters) == list(sa.parameters)
            assert [p.annotation for p in ss.parameters.values()] == [p.annotation for p in sa.parameters.values()]
            assert s.__doc__ == a.__doc__ and s.__name__ == a.__name__ == name
            if not name.startswith("iter_"):
                assert inspect.iscoroutinefunction(a) and not inspect.iscoroutinefunction(s)


class _Capture:
    def __init__(self) -> None:
        self.requests: list[httpx2.Request] = []

    def __call__(self, r: httpx2.Request) -> httpx2.Response:
        self.requests.append(r)
        if r.method == "DELETE":
            return httpx2.Response(204)
        if r.url.path.endswith("/report"):
            return httpx2.Response(200, content=b"plain text", headers={"content-type": "text/plain"})
        if r.url.path.endswith("/pets") and r.method == "GET":
            return httpx2.Response(200, json={"items": []} if "/v3/" in r.url.path else {"payload": {"Pets": []}})
        if r.url.path.endswith("/pets") and r.method == "POST":
            return httpx2.Response(201, json={"id": 1, **json.loads(r.content)})
        if "/pets/" in r.url.path and r.method == "GET":
            return httpx2.Response(200, json={"id": 7, "name": "n"})
        return httpx2.Response(204)  # empty body -> None, whatever the declared type

    @property
    def last(self) -> httpx2.Request:
        return self.requests[-1]


@pytest.fixture
def cap() -> _Capture:
    return _Capture()


@pytest.fixture
def client(cap: _Capture) -> Client:
    return Client(base_url=BASE, transport=httpx2.MockTransport(cap), max_retries=0, throttle=False)


def test_url_building_styles(client: Client, cap: _Capture) -> None:
    client.petstore_v3.list_pets(limit=5, tags=["a", "b c"], status="sold")
    assert str(cap.last.url) == "https://h/v3/pets?limit=5&tags=a&tags=b+c&status=sold"
    client.petstore_v3.get_pet(pet_id=7, include=["a", "b"])
    assert str(cap.last.url) == "https://h/v3/pets/7?include=a%2Cb"  # csv, percent-encoded by httpx2
    client.petstore_v3.list_animals(ids=[1, 2, 3], since=datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc))
    assert str(cap.last.url) == "https://h/v3/animals?ids=1%7C2%7C3&since=2020-01-01T00%3A00%3A00.000Z"
    client.petstore_v3.get_label(label="a/b", filter={"x": "1", "y": "2"})
    assert str(cap.last.url) == "https://h/v3/labels/a%2Fb?filter%5Bx%5D=1&filter%5By%5D=2"
    client.petstore_v2.list_pets(tags=["a", "b"], ids=[1, 2], codes=["x", "y"], next_token="t/1")
    url = str(cap.last.url)
    assert url.startswith("https://h/v2/pets?") and set(url.split("?")[1].split("&")) == {
        "Tags=a%2Cb",
        "Ids=1",
        "Ids=2",
        "Codes=x%7Cy",
        "NextToken=t%2F1",
    }
    client.petstore_v3.list_pets(status=models.Status.PENDING)
    assert str(cap.last.url) == "https://h/v3/pets?status=pending"  # enums encode as their value


def test_none_values_are_omitted(client: Client, cap: _Capture) -> None:
    client.petstore_v3.list_pets(limit=None, tags=None, x_request_id=None)
    assert str(cap.last.url) == "https://h/v3/pets" and "x-request-id" not in cap.last.headers
    client.petstore_v3.list_pets(x_request_id="abc")
    assert cap.last.headers["x-request-id"] == "abc"


def test_bool_and_datetime_serialization() -> None:
    assert scalar(True) == "true" and scalar(False) == "false"
    assert scalar(datetime.datetime(2020, 1, 2, 3, 4, 5)) == "2020-01-02T03:04:05.000Z"
    assert (
        scalar(datetime.datetime(2020, 1, 2, 3, 4, 5, tzinfo=datetime.timezone(datetime.timedelta(hours=2))))
        == "2020-01-02T03:04:05.000+02:00"
    )
    assert scalar(datetime.date(2020, 1, 2)) == "2020-01-02"
    assert scalar(3.5) == "3.5" and scalar(models.Status.SOLD) == "sold"


def test_unexpected_and_missing_arguments(client: Client) -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        client.petstore_v3.get_pet(pet_id=1, bogus=2)  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="missing 1 required positional argument: 'pet_id'"):
        client.petstore_v3.get_pet()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        client.petstore_v3.list_pets(10)  # type: ignore[misc]  # optional parameters are keyword-only


def test_body_encoding(client: Client, cap: _Capture) -> None:
    client.petstore_v3.create_pet(body=models.NewPet(name="n", tag=None))
    assert cap.last.content == b'{"name":"n"}' and cap.last.headers["content-type"] == "application/json"
    client.petstore_v3.create_pet(body={"name": "n", "status": "sold"})
    assert cap.last.content == b'{"name":"n","status":"sold"}'
    client.petstore_v3.update_pet_photo(pet_id=1, body=b"\x00\x01")
    assert cap.last.content == b"\x00\x01" and cap.last.headers["content-type"] == "application/octet-stream"
    client.petstore_v2.create_pet_photo(pet_id=1, body={"file": ("p.png", b"img")})
    assert cap.last.headers["content-type"].startswith("multipart/form-data") and b"img" in cap.last.read()
    with pytest.raises(TypeError, match="missing 1 required positional argument: 'body'"):
        client.petstore_v3.create_pet()  # type: ignore[call-arg]


def test_decoding(client: Client) -> None:
    assert client.petstore_v3.delete_pet(pet_id=1) is None
    assert client.petstore_v2.list_report() == "plain text"
    pet = client.petstore_v3.create_pet(body={"name": "n"})
    assert isinstance(pet, models.Pet) and pet.id == 1
    assert isinstance(client.petstore_v3.get_pet(pet_id=7), models.Pet)
    assert isinstance(client.petstore_v2.list_pets(), sw2.GetPetsResponse)


def test_error_schema_decoding() -> None:
    def handler(r: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json={"code": "NF", "message": "nope"})

    api = Client(base_url=BASE, transport=httpx2.MockTransport(handler), max_retries=0).petstore_v3
    with pytest.raises(errors.NotFoundError) as ei:
        api.get_pet(pet_id=1)
    assert isinstance(ei.value.body, models.Error) and ei.value.body.code == "NF"


def test_pagination_flags() -> None:
    paginated = {k for k, v in OPERATIONS.items() if v[3]}
    assert paginated == {"petstore_v3.listPets", "petstore_v2.listPets", "petstore_v2.getOrders"}
    assert not hasattr(PetstoreV3Resource, "iter_list_audit")  # two arrays -> ambiguous, left unpaginated
    assert hasattr(PetstoreV2Resource, "iter_list_orders")
    assert not hasattr(PetstoreV3Resource, "iter_get_pet")


def test_async_client_parity() -> None:
    cap = _Capture()
    aclient = AsyncClient(base_url=BASE, transport=httpx2.MockTransport(cap), max_retries=0, throttle=False)

    async def go() -> Any:
        pet = await aclient.petstore_v3.create_pet(body={"name": "n"})
        await aclient.petstore_v3.get_pet(pet_id=7, include=["a", "b"])
        return pet

    import asyncio

    assert asyncio.run(go()).id == 1
    assert str(cap.last.url) == "https://h/v3/pets/7?include=a%2Cb"
