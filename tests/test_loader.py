from __future__ import annotations

import json
import pathlib

import pytest

from amzn_selling_partner.spec import Document, Schema, load_document
from amzn_selling_partner.spec.cache import load_cached, spec_hash
from amzn_selling_partner.spec.loader import normalize

from .conftest import LISTINGS_ITEMS, OAS31, ORDERS_V0, SWAGGER2, requires_amazon


def test_openapi31_document() -> None:
    doc = load_document(OAS31)
    assert doc.format == "openapi3"
    assert doc.title == "Petstore"
    assert [s.url for s in doc.servers] == ["https://api.example.com/v1"]
    ops = {op.operation_id: op for op in doc.operations}
    assert set(ops) >= {"listPets", "createPet", "getPet", "deletePet", "uploadPhoto", "listAnimals"}
    lp = ops["listPets"]
    params = {p.name: p for p in lp.parameters}
    assert params["tags"].style == "form" and params["tags"].explode is True
    assert params["X-Request-Id"].location == "header"
    assert lp.responses["200"].json_schema is not None and lp.responses["200"].json_schema.ref == "PetList"
    assert lp.responses["default"].json_schema is not None and lp.responses["default"].json_schema.ref == "Error"
    # path-level parameter merged into the operation
    gp = ops["getPet"]
    assert [p.name for p in gp.parameters if p.location == "path"] == ["petId"]
    assert gp.parameters[0].required
    body = ops["createPet"].request_body
    assert body is not None and body.required and body.json_schema is not None and body.json_schema.ref == "NewPet"
    bin_body = ops["uploadPhoto"].request_body
    assert bin_body is not None and list(bin_body.content) == ["application/octet-stream"]
    assert ops["deletePet"].responses["204"].content == {}


def test_openapi31_schemas() -> None:
    doc = load_document(OAS31)
    pet = doc.schemas["Pet"]
    assert pet.type == "object" and pet.required == {"id", "name"}
    assert pet.properties["tag"].nullable and pet.properties["tag"].type == "string"
    assert pet.properties["createdAt"].format == "date-time"
    assert pet.properties["metadata"].additional_properties == Schema(type="string")
    assert pet.properties["category"].ref == "Category"
    animal = doc.schemas["Animal"]
    assert [v.ref for v in animal.one_of] == ["Dog", "Cat"]
    assert animal.discriminator is not None
    assert animal.discriminator.property_name == "kind"
    assert animal.discriminator.mapping == {"dog": "Dog", "cat": "Cat"}
    assert doc.schemas["Dog"].properties["kind"].has_const and doc.schemas["Dog"].properties["kind"].const == "dog"
    derived = doc.schemas["Derived"]
    assert derived.all_of[0].ref == "Base" and "extra" in derived.all_of[1].properties
    # recursion is by name
    assert doc.schemas["Node"].properties["children"].items is not None
    assert doc.schemas["Node"].properties["children"].items.ref == "Node"
    assert doc.resolve(Schema(ref="Node")) is doc.schemas["Node"]


def test_swagger2_document() -> None:
    doc = load_document(SWAGGER2)
    assert doc.format == "swagger2"
    assert [s.url for s in doc.servers] == ["https://api.example.com/v1"]  # trailing slash stripped
    ops = {op.operation_id: op for op in doc.operations}
    lp = ops["listPets"]
    params = {p.name: p for p in lp.parameters}
    assert (params["Tags"].style, params["Tags"].explode) == ("form", False)  # csv
    assert (params["Ids"].style, params["Ids"].explode) == ("form", True)  # multi
    assert (params["Codes"].style, params["Codes"].explode) == ("pipeDelimited", False)
    assert lp.responses["200"].content.keys() == {"application/json"}
    assert lp.responses["200"].headers["x-request-id"].type == "string"
    # body parameter -> RequestBody with consumes
    body = ops["createPet"].request_body
    assert body is not None and body.required and body.json_schema is not None and body.json_schema.ref == "NewPet"
    # $ref parameters and responses resolve
    assert ops["getPet"].parameters[0].name == "petId" and ops["getPet"].parameters[0].location == "path"
    assert ops["getPet"].responses["404"].json_schema is not None
    assert ops["getPet"].responses["404"].json_schema.ref == "ErrorList"
    # formData -> multipart request body with the file as binary
    up = ops["uploadPhoto"].request_body
    assert up is not None and list(up.content) == ["multipart/form-data"]
    form = up.content["multipart/form-data"]
    assert form.properties["file"].format == "binary" and form.required == {"file"}
    # produces text/plain
    assert list(ops["getReport"].responses["200"].content) == ["text/plain"]
    assert ops["getReport"].responses["200"].json_schema is None


def test_swagger2_schemas() -> None:
    doc = load_document(SWAGGER2)
    pet = doc.schemas["Pet"]
    assert pet.properties["Tag"].nullable  # x-nullable
    assert pet.properties["Price"].ref == "Decimal" and doc.schemas["Decimal"].type == "string"
    assert pet.properties["Parent"].ref == "Pet"
    assert pet.properties["Attributes"].additional_properties is True
    assert doc.schemas["PetList"].type == "array" and doc.schemas["PetList"].items is not None
    assert doc.schemas["PetList"].items.ref == "Pet"


def test_extensions_preserved(tmp_path: pathlib.Path) -> None:
    raw = json.loads(SWAGGER2.read_text())
    raw["x-root"] = 1
    raw["paths"]["/pets"]["get"]["x-op"] = {"a": 1}
    raw["paths"]["/pets"]["get"]["responses"]["200"]["x-resp"] = [1]
    raw["definitions"]["Pet"]["x-schema"] = "s"
    doc = normalize(raw, source="mem.json", digest="x")
    assert doc.extensions == {"x-root": 1}
    op = doc.operation("listPets")
    assert op.extensions == {"x-op": {"a": 1}}
    assert op.responses["200"].extensions == {"x-resp": [1]}
    assert doc.schemas["Pet"].extensions == {"x-schema": "s"}


def test_relative_external_refs(tmp_path: pathlib.Path) -> None:
    (tmp_path / "common.json").write_text(
        json.dumps(
            {"definitions": {"Money": {"type": "object", "properties": {"amount": {"type": "string"}}}, "Error": {"type": "string"}}}
        )
    )
    main = {
        "swagger": "2.0",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/x": {
                "get": {
                    "operationId": "getX",
                    "responses": {"200": {"description": "ok", "schema": {"$ref": "common.json#/definitions/Money"}}},
                }
            }
        },
        "definitions": {
            "Error": {"type": "object", "properties": {"msg": {"type": "string"}, "money": {"$ref": "./common.json#/definitions/Money"}}}
        },
    }
    (tmp_path / "main.json").write_text(json.dumps(main))
    doc = load_document(tmp_path / "main.json", use_cache=False)
    assert "Money" in doc.schemas and doc.schemas["Money"].properties["amount"].type == "string"
    assert doc.operation("getX").responses["200"].json_schema.ref == "Money"  # type: ignore[union-attr]
    assert doc.schemas["Error"].properties["money"].ref == "Money"


def test_ir_cache_roundtrip(tmp_path: pathlib.Path) -> None:
    digest = spec_hash(OAS31.read_bytes())
    doc = load_document(OAS31)
    cached = load_cached(digest)
    assert isinstance(cached, Document)
    assert cached == doc
    assert cached.hash == digest


def test_missing_operation_id_gets_synthetic_name() -> None:
    raw = {
        "openapi": "3.1.0",
        "info": {"title": "t", "version": "1"},
        "paths": {"/a/b": {"get": {"responses": {"204": {"description": "x"}}}}},
    }
    doc = normalize(raw, source="mem.json", digest="x")
    assert doc.operations[0].operation_id == "get_/a/b"


def test_jsonschema_document(tmp_path: pathlib.Path) -> None:
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema",
        "title": "Order Change",
        "type": "object",
        "required": ["id"],
        "properties": {"id": {"type": "string"}, "money": {"$ref": "#/definitions/Money"}},
        "definitions": {"Money": {"type": "object", "properties": {"amount": {"type": "number"}}}},
    }
    p = tmp_path / "OrderChange.json"
    p.write_text(json.dumps(schema))
    doc = load_document(p, use_cache=False)
    assert doc.format == "jsonschema"
    assert doc.annotations["root_schema"] == "OrderChange"
    assert doc.schemas["OrderChange"].properties["money"].ref == "Money"


@requires_amazon
@pytest.mark.parametrize("path", [ORDERS_V0, LISTINGS_ITEMS])
def test_amazon_specs_load(path: pathlib.Path) -> None:
    doc = load_document(path)
    assert doc.format == "swagger2"
    assert all(op.operation_id for op in doc.operations)
    assert all(r.json_schema is None or r.json_schema.ref for op in doc.operations for r in op.responses.values())
