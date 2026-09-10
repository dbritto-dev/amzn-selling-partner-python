from __future__ import annotations

import datetime
import inspect

import pytest

from spapi.compile.models import build_models
from spapi.compile.operations import compile_operations
from spapi.runtime import NOT_GIVEN, Pagination
from spapi.spec import load_document

from .conftest import OAS31, SWAGGER2


@pytest.fixture(scope="module")
def oas():
    doc = load_document(OAS31)
    ns = build_models(doc, key="ops_oas31")
    return {op.name: op for op in compile_operations(doc, ns, key_prefix="petstore.v1")}


@pytest.fixture(scope="module")
def sw2():
    doc = load_document(SWAGGER2)
    ns = build_models(doc, key="ops_sw2")
    return {op.name: op for op in compile_operations(doc, ns, key_prefix="petstore2.v1")}


def test_method_and_param_names(oas) -> None:
    assert set(oas) == {"list_pets", "create_pet", "get_pet", "delete_pet", "upload_photo", "list_animals", "get_tree", "list_audit", "stream_events", "get_by_label"}
    lp = oas["list_pets"]
    assert [p.py_name for p in lp.query_params] == ["limit", "tags", "status", "next_token"]
    assert [p.py_name for p in lp.header_params] == ["x_request_id"]
    assert lp.key == "petstore.v1.listPets" and lp.method == "GET"


def test_url_building_styles(oas, sw2) -> None:
    assert oas["list_pets"].build_url("https://h/v1", {"limit": 5, "tags": ["a", "b c"], "status": "sold"}) == "https://h/v1/pets?limit=5&tags=a&tags=b%20c&status=sold"
    assert oas["get_pet"].build_url("", {"pet_id": 7, "include": ["a", "b"]}) == "/pets/7?include=a,b"
    assert oas["list_animals"].build_url("", {"ids": [1, 2, 3], "since": datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)}) == "/animals?ids=1%7C2%7C3&since=2020-01-01T00%3A00%3A00.000Z"
    assert oas["get_by_label"].build_url("", {"label": "a/b", "filter": {"x": "1", "y": "2"}}) == "/labels/.a%2Fb?filter%5Bx%5D=1&filter%5By%5D=2"
    assert sw2["list_pets"].build_url("", {"tags": ["a", "b"], "ids": [1, 2], "codes": ["x", "y"], "next_token": "t/1"}) == "/pets?Tags=a,b&Ids=1&Ids=2&Codes=x%7Cy&NextToken=t%2F1"
    assert sw2["list_pets"].build_url("", {"ids": "single"}) == "/pets?Ids=single"


def test_not_given_and_none_are_omitted(oas) -> None:
    assert oas["list_pets"].build_url("", {"limit": NOT_GIVEN, "tags": None}) == "/pets"
    assert oas["list_pets"].build_headers({"x_request_id": NOT_GIVEN}) == ()
    assert oas["list_pets"].build_headers({"x_request_id": "abc"}) == (("X-Request-Id", "abc"),)


def test_bool_and_datetime_serialization(oas) -> None:
    from spapi.compile._serializers import scalar

    assert scalar(True) == "true" and scalar(False) == "false"
    assert scalar(datetime.datetime(2020, 1, 2, 3, 4, 5)) == "2020-01-02T03:04:05.000Z"
    assert scalar(datetime.datetime(2020, 1, 2, 3, 4, 5, tzinfo=datetime.timezone(datetime.timedelta(hours=2)))) == "2020-01-02T03:04:05.000+02:00"
    assert scalar(datetime.date(2020, 1, 2)) == "2020-01-02"
    assert scalar(3.5) == "3.5"


def test_unexpected_and_missing_arguments(oas) -> None:
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        oas["get_pet"].check_kwargs({"pet_id": 1, "bogus": 2})
    with pytest.raises(TypeError, match="missing required keyword argument: 'pet_id'"):
        oas["get_pet"].check_kwargs({})
    with pytest.raises(TypeError, match="missing required keyword argument: 'pet_id'"):
        oas["get_pet"].check_kwargs({"pet_id": NOT_GIVEN})
    oas["get_pet"].check_kwargs({"pet_id": 1})


def test_body_encoding(oas, sw2) -> None:
    ns_pet = oas["create_pet"].body.annotation
    assert oas["create_pet"].encode_body(ns_pet(name="n", tag=None)) == (b'{"name":"n"}', "application/json")
    assert oas["create_pet"].encode_body({"name": "n", "status": "sold"}) == (b'{"name":"n","status":"sold"}', "application/json")
    with pytest.raises(TypeError, match="missing required argument: 'body'"):
        oas["create_pet"].encode_body(NOT_GIVEN)
    assert oas["upload_photo"].encode_body(b"\x00\x01") == (b"\x00\x01", "application/octet-stream")
    assert oas["upload_photo"].body.annotation is bytes
    assert sw2["upload_photo"].body.kind == "multipart"
    assert oas["get_pet"].encode_body(NOT_GIVEN) is None


def test_signature(oas) -> None:
    sig = oas["list_pets"].signature
    params = list(sig.parameters.values())
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params)
    assert [p.name for p in params] == ["limit", "tags", "status", "next_token", "x_request_id", "raw", "paginate", "request_options"]
    assert sig.parameters["limit"].default is NOT_GIVEN
    assert sig.parameters["limit"].annotation == int | type(NOT_GIVEN)
    gp = oas["get_pet"].signature
    assert gp.parameters["pet_id"].default is inspect.Parameter.empty and gp.parameters["pet_id"].annotation is int
    assert gp.return_annotation.__name__ == "Pet"
    assert oas["delete_pet"].signature.return_annotation is None
    cp = oas["create_pet"].signature
    assert list(cp.parameters)[0] == "body" and cp.parameters["body"].default is inspect.Parameter.empty


def test_decoders(oas, sw2) -> None:
    assert oas["get_pet"].decoders[200].kind == "json"
    assert oas["delete_pet"].decoders[204].kind == "none"
    assert oas["create_pet"].decoders[201].kind == "json" and oas["create_pet"].default_decoder.kind == "json"
    assert oas["create_pet"].default_decoder.decode(b'{"id":1,"name":"n"}', lambda: "").id == 1
    assert oas["stream_events"].stream_default is True
    assert sw2["get_report"].decoders[200].kind == "text"
    assert oas["get_pet"].error_decoders[404] is not None and oas["get_pet"].default_error is not None
    assert oas["list_pets"].default_error is not None  # from "default" response


def test_pagination_detection(oas, sw2) -> None:
    p = oas["list_pets"].pagination
    assert p is not None and p.descriptor == Pagination(items_path="items", next_token_path="nextToken", next_token_param="nextToken", source="heuristic")
    assert p.token_kw == "next_token"
    assert oas["list_audit"].pagination is None  # two arrays -> ambiguous
    assert oas["get_pet"].pagination is None
    sp = sw2["list_pets"].pagination
    assert sp is not None and sp.descriptor.items_path == "payload.Pets" and sp.descriptor.next_token_path == "payload.NextToken"
    so = sw2["get_orders"].pagination
    assert so is not None and so.descriptor.items_path == "payload.orders" and so.descriptor.next_token_path == "payload.pagination.nextToken"
    assert so.keep_kws == frozenset()


def test_pagination_getters(sw2) -> None:
    p = sw2["list_pets"].pagination
    assert p is not None
    assert p.items_raw({"payload": {"Pets": [1], "NextToken": "t"}}) == [1]
    assert p.token_raw({"payload": {"NextToken": "t"}}) == "t"
    assert p.token_raw({}) is None
    ns = build_models(load_document(SWAGGER2), key="ops_sw2")
    resp = ns.GetPetsResponse.model_validate({"payload": {"Pets": [{"Id": 1, "Name": "n"}], "NextToken": "t"}})
    assert p.items_model(resp)[0].id == 1 and p.token_model(resp) == "t"
    assert p.next_kwargs({"limit": 1, "tags": ["a"]}, "t2") == {"limit": 1, "tags": ["a"], "next_token": "t2"}


def test_plugin_pagination_override_and_disable() -> None:
    doc = load_document(OAS31)
    ns = build_models(doc, key="ops_override")
    listing = doc.operation("listAudit").annotated(pagination=Pagination(items_path="events", next_token_path="nextToken", next_token_param="nextToken", drop_params_on_next=True))
    off = doc.operation("listPets").annotated(pagination=None)
    doc2 = doc.with_operations((listing, off))
    ops = {op.name: op for op in compile_operations(doc2, ns, key_prefix="x")}
    assert ops["list_audit"].pagination is not None and ops["list_audit"].pagination.descriptor.drop_params_on_next
    assert ops["list_audit"].pagination.next_kwargs({"next_token": "a"}, "b") == {"next_token": "b"}
    assert ops["list_pets"].pagination is None


def test_duplicate_operation_ids_get_method_suffix() -> None:
    from spapi.spec.loader import normalize

    raw = {"openapi": "3.1.0", "info": {"title": "t", "version": "1"}, "paths": {"/a": {"put": {"operationId": "link", "responses": {"204": {"description": "x"}}}, "post": {"operationId": "link", "responses": {"204": {"description": "x"}}}}}}
    doc = normalize(raw, source="mem.json", digest="dupop")
    names = [op.name for op in compile_operations(doc, build_models(doc, key="dupop"), key_prefix="d")]
    assert names == ["link", "link_post"]


def test_rate_limit_annotation_required_type() -> None:
    doc = load_document(OAS31)
    bad = doc.with_operations((doc.operation("getPet").annotated(rate_limit="fast"),))
    with pytest.raises(TypeError):
        compile_operations(bad, build_models(doc, key="rl"), key_prefix="x")
