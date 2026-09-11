"""Generated ``Op`` tables (the petstore test package, tests/petstore_sdk)."""

from __future__ import annotations

import datetime
import inspect

import httpx2
import pytest
from petstore_sdk.client import AsyncClient, Client
from petstore_sdk.models.petstore import v2 as sw2_models
from petstore_sdk.models.petstore import v3 as models
from petstore_sdk.resources.petstore.v2 import PetstoreV2
from petstore_sdk.resources.petstore.v3 import AsyncPetstoreV3, PetstoreV3

from amzn_selling_partner.runtime import NOT_GIVEN, Pagination
from amzn_selling_partner.runtime._op import Op
from amzn_selling_partner.runtime._serializers import scalar

_client = Client(base_url="https://h/v1", transport=httpx2.MockTransport(lambda r: httpx2.Response(500)))


@pytest.fixture(scope="module")
def oas() -> dict[str, Op]:
    return dict(PetstoreV3._ops)


@pytest.fixture(scope="module")
def sw2() -> dict[str, Op]:
    return dict(PetstoreV2._ops)


def test_method_and_param_names(oas: dict[str, Op]) -> None:
    assert set(oas) == {
        "list_pets",
        "create_pet",
        "get_pet",
        "delete_pet",
        "upload_photo",
        "list_animals",
        "get_tree",
        "list_audit",
        "stream_events",
        "get_by_label",
    }
    lp = oas["list_pets"]
    assert [p.py_name for p in lp.query_params] == ["limit", "tags", "status", "next_token"]
    assert [p.py_name for p in lp.header_params] == ["x_request_id"]
    assert lp.key == "petstore.v3.listPets" and lp.method == "GET" and lp.api == "petstore" and lp.version == "v3"


def test_url_building_styles(oas: dict[str, Op], sw2: dict[str, Op]) -> None:
    assert (
        oas["list_pets"].build_url("https://h/v1", {"limit": 5, "tags": ["a", "b c"], "status": "sold"})
        == "https://h/v1/pets?limit=5&tags=a&tags=b%20c&status=sold"
    )
    assert oas["get_pet"].build_url("", {"pet_id": 7, "include": ["a", "b"]}) == "/pets/7?include=a,b"
    assert (
        oas["list_animals"].build_url("", {"ids": [1, 2, 3], "since": datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)})
        == "/animals?ids=1%7C2%7C3&since=2020-01-01T00%3A00%3A00.000Z"
    )
    assert (
        oas["get_by_label"].build_url("", {"label": "a/b", "filter": {"x": "1", "y": "2"}})
        == "/labels/.a%2Fb?filter%5Bx%5D=1&filter%5By%5D=2"
    )
    assert (
        sw2["list_pets"].build_url("", {"tags": ["a", "b"], "ids": [1, 2], "codes": ["x", "y"], "next_token": "t/1"})
        == "/pets?Tags=a,b&Ids=1&Ids=2&Codes=x%7Cy&NextToken=t%2F1"
    )
    assert sw2["list_pets"].build_url("", {"ids": "single"}) == "/pets?Ids=single"


def test_not_given_and_none_are_omitted(oas: dict[str, Op]) -> None:
    assert oas["list_pets"].build_url("", {"limit": NOT_GIVEN, "tags": None}) == "/pets"
    assert oas["list_pets"].build_headers({"x_request_id": NOT_GIVEN}) == ()
    assert oas["list_pets"].build_headers({"x_request_id": "abc"}) == (("X-Request-Id", "abc"),)


def test_bool_and_datetime_serialization() -> None:
    assert scalar(True) == "true" and scalar(False) == "false"
    assert scalar(datetime.datetime(2020, 1, 2, 3, 4, 5)) == "2020-01-02T03:04:05.000Z"
    assert (
        scalar(datetime.datetime(2020, 1, 2, 3, 4, 5, tzinfo=datetime.timezone(datetime.timedelta(hours=2))))
        == "2020-01-02T03:04:05.000+02:00"
    )
    assert scalar(datetime.date(2020, 1, 2)) == "2020-01-02"
    assert scalar(3.5) == "3.5"


def test_unexpected_and_missing_arguments(oas: dict[str, Op]) -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        oas["get_pet"].check_kwargs({"pet_id": 1, "bogus": 2})
    with pytest.raises(TypeError, match="missing required keyword argument: 'pet_id'"):
        oas["get_pet"].check_kwargs({})
    with pytest.raises(TypeError, match="missing required keyword argument: 'pet_id'"):
        oas["get_pet"].check_kwargs({"pet_id": NOT_GIVEN})
    oas["get_pet"].check_kwargs({"pet_id": 1})
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        _client.petstore.v3.get_pet(pet_id=1, bogus=2)  # type: ignore[call-arg]


def test_body_encoding(oas: dict[str, Op], sw2: dict[str, Op]) -> None:
    create = oas["create_pet"]
    assert create.body is not None and create.body.kind == "json" and create.body.required
    assert create.encode_body(models.NewPet(name="n", tag=None)) == (b'{"name":"n"}', "application/json")
    assert create.encode_body({"name": "n", "status": "sold"}) == (b'{"name":"n","status":"sold"}', "application/json")
    with pytest.raises(TypeError, match="missing required argument: 'body'"):
        create.encode_body(NOT_GIVEN)
    upload = oas["upload_photo"]
    assert upload.body is not None and upload.body.kind == "binary"
    assert upload.encode_body(b"\x00\x01") == (b"\x00\x01", "application/octet-stream")
    assert sw2["upload_photo"].body is not None and sw2["upload_photo"].body.kind == "multipart"
    assert oas["get_pet"].encode_body(NOT_GIVEN) is None


def test_signature() -> None:
    sig = inspect.signature(PetstoreV3.list_pets)
    params = [p for p in sig.parameters.values() if p.name != "self"]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params)
    assert [p.name for p in params] == ["limit", "tags", "status", "next_token", "x_request_id", "raw", "paginate", "request_options"]
    assert sig.parameters["limit"].default is NOT_GIVEN
    assert sig.parameters["limit"].annotation == "int | NotGiven"
    assert sig.parameters["status"].annotation == "models.Status | NotGiven"
    assert sig.return_annotation == "SyncPage[models.Pet]"
    assert inspect.signature(AsyncPetstoreV3.list_pets).return_annotation == "AsyncPage[models.Pet]"
    gp = inspect.signature(PetstoreV3.get_pet)
    assert gp.parameters["pet_id"].default is inspect.Parameter.empty and gp.parameters["pet_id"].annotation == "int"
    assert gp.return_annotation == "models.Pet"
    assert inspect.signature(PetstoreV3.delete_pet).return_annotation == "None"
    cp = inspect.signature(PetstoreV3.create_pet)
    assert list(cp.parameters)[1] == "body" and cp.parameters["body"].default is inspect.Parameter.empty
    assert cp.parameters["body"].annotation == "models.NewPet | Mapping[str, Any]"
    assert inspect.signature(PetstoreV3.stream_events).return_annotation == "Stream"


def test_sync_async_same_methods_and_signatures() -> None:
    for sync_cls, async_cls in ((PetstoreV3, AsyncPetstoreV3), (PetstoreV2, type(AsyncClient(base_url="x").petstore.v2))):
        assert set(sync_cls._ops) == set(async_cls._ops)
        for name in sync_cls._ops:
            s, a = getattr(sync_cls, name), getattr(async_cls, name)
            ss, sa = inspect.signature(s), inspect.signature(a)
            assert list(ss.parameters) == list(sa.parameters)
            assert [p.annotation for p in ss.parameters.values()] == [p.annotation for p in sa.parameters.values()]
            assert s.__doc__ == a.__doc__ and s.__name__ == a.__name__ == name
            assert inspect.iscoroutinefunction(a) and not inspect.iscoroutinefunction(s)


def test_decoders(oas: dict[str, Op], sw2: dict[str, Op]) -> None:
    assert oas["get_pet"].decoder_for(200).kind == "json"
    assert oas["delete_pet"].decoder_for(204).kind == "none"
    assert oas["create_pet"].decoder_for(201).kind == "json" and oas["create_pet"].default_decoder.kind == "json"
    assert oas["create_pet"].default_decoder.decode(b'{"id":1,"name":"n"}', lambda: "").id == 1
    assert oas["create_pet"].default_decoder.python_type is models.Pet
    assert oas["stream_events"].stream_default is True
    assert sw2["get_report"].decoder_for(200).kind == "text"
    assert oas["get_pet"].error_decoders[404] is not None and oas["get_pet"].default_error is not None
    assert oas["list_pets"].default_error is not None  # from the "default" response
    assert oas["list_pets"].default_error.python_type is models.Error


def test_pagination_detection(oas: dict[str, Op], sw2: dict[str, Op]) -> None:
    p = oas["list_pets"].compiled_pagination
    assert p is not None and p.descriptor == Pagination(
        items_path="items", next_token_path="nextToken", next_token_param="nextToken", source="heuristic"
    )
    assert p.token_kw == "next_token"
    assert oas["list_audit"].pagination is None  # two arrays -> ambiguous
    assert oas["get_pet"].pagination is None
    sp = sw2["list_pets"].compiled_pagination
    assert sp is not None and sp.descriptor.items_path == "payload.Pets" and sp.descriptor.next_token_path == "payload.NextToken"
    so = sw2["get_orders"].compiled_pagination
    assert (
        so is not None and so.descriptor.items_path == "payload.orders" and so.descriptor.next_token_path == "payload.pagination.nextToken"
    )
    assert so.keep_kws == frozenset()


def test_pagination_getters(sw2: dict[str, Op]) -> None:
    p = sw2["list_pets"].compiled_pagination
    assert p is not None
    assert p.items_raw({"payload": {"Pets": [1], "NextToken": "t"}}) == [1]
    assert p.token_raw({"payload": {"NextToken": "t"}}) == "t"
    assert p.token_raw({}) is None
    resp = sw2_models.GetPetsResponse.model_validate({"payload": {"Pets": [{"Id": 1, "Name": "n"}], "NextToken": "t"}})
    assert p.items_model(resp)[0].id == 1 and p.token_model(resp) == "t"
    assert p.next_kwargs({"limit": 1, "tags": ["a"]}, "t2") == {"limit": 1, "tags": ["a"], "next_token": "t2"}


def test_op_literal_defaults_and_warm(oas: dict[str, Op]) -> None:
    op = Op(key="k", name="n", operation_id="n", method="GET", path="/x", url_template="/x")
    assert op.static_path and op.accepted == frozenset() and op.required == () and op.compiled_pagination is None
    assert op.build_url("https://h", {}) == "https://h/x"
    for o in oas.values():
        o.warm()
    assert oas["get_pet"].default_decoder.adapter is oas["get_pet"].default_decoder.adapter
