from __future__ import annotations

import datetime
import json

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from spapi.compile.models import build_models, clear_memo
from spapi.spec import load_document
from spapi.spec.loader import normalize

from .conftest import OAS31, ORDERS_V0, SWAGGER2, requires_amazon


@pytest.fixture
def ns():
    return build_models(load_document(OAS31), key="test_oas31")


def test_object_model_fields_and_aliases(ns) -> None:
    Pet = ns.Pet
    assert issubclass(Pet, BaseModel)
    assert Pet.__module__.startswith("spapi.models.")  # memoised per spec hash, so the first namespace wins
    fields = Pet.model_fields
    assert fields["created_at"].alias == "createdAt"
    assert fields["schema_"].alias == "schema"  # BaseModel attribute collision
    assert fields["id"].is_required() and not fields["tag"].is_required()
    assert Pet.model_config["frozen"] and Pet.model_config["extra"] == "allow"


def test_decode_and_encode_roundtrip(ns) -> None:
    body = {
        "id": 1,
        "name": "x",
        "tag": None,
        "status": "sold",
        "createdAt": "2020-01-01T00:00:00Z",
        "birthday": "2020-01-02",
        "photo": "aGVsbG8=",
        "metadata": {"k": "v"},
        "owner": {"name": "o"},
        "category": {"name": "c", "parent": {"name": "root"}},
        "schema": "s",
        "extra": 5,
    }
    pet = TypeAdapter(ns.Pet).validate_json(json.dumps(body).encode())
    assert pet.created_at == datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
    assert pet.birthday == datetime.date(2020, 1, 2)
    assert pet.photo == b"hello"
    assert pet.category.parent.name == "root"
    assert pet.schema_ == "s"
    assert pet.extra == 5  # extra="allow"
    out = json.loads(pet.model_dump_json(by_alias=True, exclude_none=True))
    assert out["createdAt"] == "2020-01-01T00:00:00Z" and out["photo"] == "aGVsbG8=" and out["schema"] == "s"
    assert "tag" not in out
    with pytest.raises(ValidationError):
        pet.name = "y"  # frozen


def test_populate_by_name(ns) -> None:
    pet = ns.Pet(id=1, name="n", created_at=datetime.datetime(2021, 1, 1))
    assert pet.created_at.year == 2021
    assert ns.Pet(id=1, name="n", createdAt="2021-01-01T00:00:00Z").created_at.year == 2021


def test_enum_literal(ns) -> None:
    with pytest.raises(ValidationError):
        ns.Pet(id=1, name="n", status="unknown")
    assert ns.Pet(id=1, name="n", status="pending").status == "pending"


def test_enum_plain_mode() -> None:
    ns = build_models(load_document(OAS31), key="test_oas31_plain", enum_mode="plain")
    assert ns.Pet(id=1, name="n", status="unknown").status == "unknown"


def test_discriminated_union(ns) -> None:
    adapter = ns.adapter_for_type(list[ns.Animal])
    animals = adapter.validate_json(b'[{"kind":"dog","barks":true},{"kind":"cat","lives":9}]')
    assert [type(a).__name__ for a in animals] == ["Dog", "Cat"]
    with pytest.raises(ValidationError):
        adapter.validate_json(b'[{"kind":"bird"}]')


def test_nullable_and_null_variant(ns) -> None:
    pet = ns.Pet(id=1, name="n", tag=None, owner=None)
    assert pet.tag is None and pet.owner is None
    assert ns.Pet.model_fields["tag"].annotation == str | None


def test_recursive_schema(ns) -> None:
    node = TypeAdapter(ns.Node).validate_json(b'{"value":"a","children":[{"value":"b","children":[{"value":"c"}]}]}')
    assert node.children[0].children[0].value == "c"
    assert ns.Category(name="a", parent=ns.Category(name="b")).parent.name == "b"


def test_all_of_merged(ns) -> None:
    assert set(ns.Derived.model_fields) == {"id", "extra"}
    assert ns.Derived.model_fields["extra"].is_required()


def test_additional_properties_and_aliases_in_namespace(ns) -> None:
    assert ns.Pet.model_fields["metadata"].annotation == dict[str, str] | None
    assert ns.PetList.model_fields["items"].annotation == list[ns.Pet]
    assert ns.Status == __import__("typing").Literal["available", "pending", "sold"]


def test_swagger2_models() -> None:
    ns = build_models(load_document(SWAGGER2), key="test_sw2")
    assert ns.Decimal is str
    assert ns.PetList == list[ns.Pet]
    resp = TypeAdapter(ns.GetPetsResponse).validate_json(
        b'{"payload":{"Pets":[{"Id":1,"Name":"n","Tag":null,"Price":"1.5","Parent":{"Id":2,"Name":"p"},"Attributes":{"a":[1]}}],"NextToken":"t"}}'
    )
    assert resp.payload.pets[0].parent.id == 2 and resp.payload.pets[0].attributes == {"a": [1]}
    assert resp.payload.next_token == "t"


def test_binary_body_type(ns) -> None:
    assert ns.type_for(load_document(OAS31).operation("uploadPhoto").request_body.content["application/octet-stream"]) is bytes


def test_type_expressions(ns) -> None:
    from spapi.compile.typenames import type_expr

    doc = ns.document
    assert type_expr(doc, doc.schemas["Pet"].properties["tags"]) == "list[str]"
    assert type_expr(doc, doc.schemas["Pet"].properties["tag"]) == "str | None"
    assert type_expr(doc, doc.schemas["Pet"].properties["createdAt"]) == "datetime.datetime"
    assert type_expr(doc, doc.schemas["Pet"].properties["metadata"]) == "dict[str, str]"
    assert type_expr(doc, doc.schemas["Pet"].properties["owner"]) == "Owner | None"
    assert type_expr(doc, doc.schemas["Animal"]) == "Dog | Cat"
    assert type_expr(doc, doc.schemas["Status"]) == "Literal['available', 'pending', 'sold']"
    assert type_expr(doc, doc.schemas["PetList"].properties["items"], model_prefix="m.") == "list[m.Pet]"
    assert type_expr(doc, doc.schemas["PetList"].properties["items"], dict_suffix="Dict") == "list[PetDict]"


def test_memoised_per_spec_hash() -> None:
    a = build_models(load_document(OAS31), key="memo_a")
    b = build_models(load_document(OAS31), key="memo_b")
    assert a.Pet is b.Pet  # same hash -> same class
    clear_memo()
    c = build_models(load_document(OAS31), key="memo_c")
    assert c.Pet is not a.Pet


def test_build_all_and_dir(ns) -> None:
    n = ns.build_all()
    assert n == len(ns.document.schemas)
    assert "Pet" in dir(ns) and "Pet" in ns


def test_duplicate_python_field_names() -> None:
    raw = {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "1"},
        "paths": {},
        "components": {
            "schemas": {"X": {"type": "object", "properties": {"marketplaceId": {"type": "string"}, "MarketplaceId": {"type": "integer"}}}}
        },
    }
    ns = build_models(normalize(raw, source="mem.json", digest="dup"), key="dup")
    fields = ns.X.model_fields
    assert set(fields) == {"marketplace_id", "marketplace_id_2"}
    x = ns.X(**{"marketplaceId": "a", "MarketplaceId": 1})
    assert (x.marketplace_id, x.marketplace_id_2) == ("a", 1)


def test_reserved_class_names() -> None:
    raw = {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "1"},
        "paths": {},
        "components": {
            "schemas": {
                "list": {"type": "object", "properties": {"a": {"type": "string"}}},
                "Holder": {
                    "type": "object",
                    "properties": {
                        "items": {"type": "array", "items": {"$ref": "#/components/schemas/list"}},
                        "me": {"$ref": "#/components/schemas/Holder"},
                    },
                },
            }
        },
    }
    ns = build_models(normalize(raw, source="mem.json", digest="reserved"), key="reserved")
    ns.build_all()
    assert ns.get("list").__name__ == "list_"
    h = ns.Holder(items=[{"a": "x"}], me={"items": []})
    assert h.items[0].a == "x"


@requires_amazon
def test_amazon_orders_models() -> None:
    ns = build_models(load_document(ORDERS_V0), key="amz_orders_v0")
    ns.build_all()
    Order = ns.Order
    assert Order.model_fields["amazon_order_id"].alias == "AmazonOrderId"
    order = Order.model_validate(
        {"AmazonOrderId": "1", "PurchaseDate": "2020-01-01T00:00:00Z", "LastUpdateDate": "2020-01-01T00:00:00Z", "OrderStatus": "Shipped"}
    )
    assert order.order_status == "Shipped"
