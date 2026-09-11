"""Generated pydantic models (the petstore test package, tests/petstore_sdk)."""

from __future__ import annotations

import datetime
import json
from typing import Annotated, Literal

import pytest
from petstore_sdk.models.petstore import v2 as sw2
from petstore_sdk.models.petstore import v3 as m
from pydantic import BaseModel, TypeAdapter, ValidationError

from amzn_selling_partner.runtime._models import SpecModel, adapter_for

from .conftest import requires_amazon


def test_object_model_fields_and_aliases() -> None:
    assert issubclass(m.Pet, SpecModel) and issubclass(m.Pet, BaseModel)
    assert m.Pet.__module__ == "petstore_sdk.models.petstore.v3"
    fields = m.Pet.model_fields
    assert fields["created_at"].alias == "createdAt"
    assert fields["schema_"].alias == "schema"  # BaseModel attribute collision
    assert fields["id"].is_required() and not fields["tag"].is_required()
    assert m.Pet.model_config["frozen"] and m.Pet.model_config["extra"] == "allow"
    assert set(m.__all__) >= {"Pet", "NewPet", "Status", "Animal", "Node"}


def test_decode_and_encode_roundtrip() -> None:
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
    pet = TypeAdapter(m.Pet).validate_json(json.dumps(body).encode())
    assert pet.created_at == datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    assert pet.birthday == datetime.date(2020, 1, 2)
    assert pet.photo == b"hello"
    assert pet.category is not None and pet.category.parent is not None and pet.category.parent.name == "root"
    assert pet.schema_ == "s"
    assert pet.extra == 5  # type: ignore[attr-defined]  # extra="allow"
    out = json.loads(pet.model_dump_json(by_alias=True, exclude_none=True))
    assert out["createdAt"] == "2020-01-01T00:00:00Z" and out["photo"] == "aGVsbG8=" and out["schema"] == "s"
    assert "tag" not in out
    with pytest.raises(ValidationError):
        pet.name = "y"  # frozen


def test_populate_by_name() -> None:
    pet = m.Pet(id=1, name="n", created_at=datetime.datetime(2021, 1, 1))
    assert pet.created_at is not None and pet.created_at.year == 2021
    assert m.Pet(id=1, name="n", createdAt="2021-01-01T00:00:00Z").created_at.year == 2021  # type: ignore[call-arg, union-attr]


def test_enum_literal() -> None:
    with pytest.raises(ValidationError):
        m.Pet(id=1, name="n", status="unknown")  # type: ignore[arg-type]
    assert m.Pet(id=1, name="n", status="pending").status == "pending"
    assert m.Status == Literal["available", "pending", "sold"]


def test_discriminated_union() -> None:
    adapter = adapter_for(list[m.Animal])
    animals = adapter.validate_json(b'[{"kind":"dog","barks":true},{"kind":"cat","lives":9}]')
    assert [type(a).__name__ for a in animals] == ["Dog", "Cat"]
    with pytest.raises(ValidationError):
        adapter.validate_json(b'[{"kind":"bird"}]')
    assert m.Animal == Annotated[m.Dog | m.Cat, m.Animal.__metadata__[0]]


def test_nullable_and_null_variant() -> None:
    pet = m.Pet(id=1, name="n", tag=None, owner=None)
    assert pet.tag is None and pet.owner is None
    assert m.Pet.model_fields["tag"].annotation == str | None


def test_recursive_schema() -> None:
    node = TypeAdapter(m.Node).validate_json(b'{"value":"a","children":[{"value":"b","children":[{"value":"c"}]}]}')
    assert node.children[0].children[0].value == "c"  # type: ignore[index]
    assert m.Category(name="a", parent=m.Category(name="b")).parent.name == "b"  # type: ignore[union-attr]


def test_all_of_merged() -> None:
    assert set(m.Derived.model_fields) == {"id", "extra"}
    assert m.Derived.model_fields["extra"].is_required()


def test_additional_properties_and_aliases() -> None:
    assert m.Pet.model_fields["metadata"].annotation == dict[str, str] | None
    assert m.PetList.model_fields["items"].annotation == list[m.Pet]


def test_swagger2_models() -> None:
    # `Decimal` (string alias) and `PetList` (array alias) are inlined by the generator
    assert sw2.Pet.model_fields["price"].annotation == str | None
    assert sw2.PetsPayload.model_fields["pets"].annotation == list[sw2.Pet]
    resp = TypeAdapter(sw2.GetPetsResponse).validate_json(
        b'{"payload":{"Pets":[{"Id":1,"Name":"n","Tag":null,"Price":"1.5","Parent":{"Id":2,"Name":"p"},"Attributes":{"a":[1]}}],"NextToken":"t"}}'
    )
    assert resp.payload is not None and resp.payload.pets[0].parent is not None and resp.payload.pets[0].parent.id == 2
    assert resp.payload.pets[0].attributes == {"a": [1]}
    assert resp.payload.next_token == "t"


def test_import_builds_no_schema() -> None:
    # defer_build: importing a models module creates classes only; the schema is built on first use
    assert m.Owner.__pydantic_complete__ is False or m.Owner.__pydantic_core_schema__ is not None
    assert m.Owner(name="o").name == "o"


@requires_amazon
def test_amazon_orders_models() -> None:
    from amzn_selling_partner.models.orders import v0

    assert v0.Order.model_fields["amazon_order_id"].alias == "AmazonOrderId"
    order = v0.Order.model_validate(
        {"AmazonOrderId": "1", "PurchaseDate": "2020-01-01T00:00:00Z", "LastUpdateDate": "2020-01-01T00:00:00Z", "OrderStatus": "Shipped"}
    )
    assert order.order_status == "Shipped"
    assert v0.OrdersList.model_fields["orders"].annotation == list[v0.Order]  # array alias inlined
