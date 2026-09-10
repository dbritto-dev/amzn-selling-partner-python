"""Hypothesis fuzzing of the parameter serializers."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote

from hypothesis import given, settings
from hypothesis import strategies as st

from spapi.compile._serializers import header_serializer, path_serializer, query_serializer, scalar
from spapi.spec.ir import Parameter, Schema

text = st.text(min_size=0, max_size=30)
scalars = st.one_of(text, st.integers(), st.booleans(), st.floats(allow_nan=False, allow_infinity=False))


def _resolve(s: Schema) -> Schema:
    return s


def _param(name: str, location: str, schema: Schema, style: str, explode: bool, allow_reserved: bool = False) -> Parameter:
    return Parameter(name=name, location=location, schema=schema, style=style, explode=explode, allow_reserved=allow_reserved)  # type: ignore[arg-type]


@given(name=st.from_regex(r"[A-Za-z][A-Za-z0-9_-]{0,10}", fullmatch=True), value=scalars)
@settings(max_examples=200)
def test_query_scalar_roundtrip(name: str, value: object) -> None:
    enc = query_serializer(_param(name, "query", Schema(type="string"), "form", True), _resolve)(value)
    assert parse_qs(enc, keep_blank_values=True) == {name: [scalar(value)]}


@given(name=st.from_regex(r"[A-Za-z][A-Za-z0-9_]{0,10}", fullmatch=True), values=st.lists(text, min_size=1, max_size=5))
@settings(max_examples=200)
def test_query_array_explode_roundtrip(name: str, values: list[str]) -> None:
    enc = query_serializer(_param(name, "query", Schema(type="array", items=Schema(type="string")), "form", True), _resolve)(values)
    assert parse_qs(enc, keep_blank_values=True) == {name: values}


@given(values=st.lists(text.filter(lambda s: "," not in s), min_size=1, max_size=5))
@settings(max_examples=200)
def test_query_array_csv_roundtrip(values: list[str]) -> None:
    enc = query_serializer(_param("k", "query", Schema(type="array", items=Schema(type="string")), "form", False), _resolve)(values)
    assert parse_qs(enc, keep_blank_values=True) == {"k": [",".join(values)]}
    # joining commas stay unencoded, commas inside values are encoded
    assert enc.count(",") == len(values) - 1


@given(values=st.lists(text, min_size=1, max_size=5), style=st.sampled_from(["pipeDelimited", "spaceDelimited"]))
@settings(max_examples=100)
def test_query_delimited(values: list[str], style: str) -> None:
    enc = query_serializer(_param("k", "query", Schema(type="array", items=Schema(type="string")), style, False), _resolve)(values)
    delim = "|" if style == "pipeDelimited" else " "
    assert parse_qs(enc, keep_blank_values=True) == {"k": [delim.join(values)]}


@given(value=scalars)
@settings(max_examples=200)
def test_path_scalar_is_single_segment(value: object) -> None:
    enc = path_serializer(_param("id", "path", Schema(type="string"), "simple", False), _resolve)(value)
    assert "/" not in enc and "?" not in enc and "#" not in enc and " " not in enc
    assert unquote(enc) == scalar(value)


@given(value=text)
def test_path_allow_reserved_keeps_slash(value: str) -> None:
    enc = path_serializer(_param("r", "path", Schema(type="string"), "simple", False, allow_reserved=True), _resolve)(value)
    assert unquote(enc) == value
    assert enc.count("/") == value.count("/")


@given(values=st.lists(st.from_regex(r"[a-z0-9]{1,5}", fullmatch=True), min_size=1, max_size=4), explode=st.booleans())
def test_path_label_and_matrix(values: list[str], explode: bool) -> None:
    label = path_serializer(_param("l", "path", Schema(type="array", items=Schema(type="string")), "label", explode), _resolve)(values)
    assert label == "." + ("." if explode else ",").join(values)
    matrix = path_serializer(_param("m", "path", Schema(type="array", items=Schema(type="string")), "matrix", explode), _resolve)(values)
    assert matrix == (";m=" + ";m=".join(values) if explode else ";m=" + ",".join(values))


@given(values=st.lists(st.from_regex(r"[\x21-\x7e]{1,8}", fullmatch=True).filter(lambda s: "," not in s), min_size=1, max_size=4))
def test_header_array_simple(values: list[str]) -> None:
    enc = header_serializer(_param("h", "header", Schema(type="array", items=Schema(type="string")), "simple", False), _resolve)(values)
    assert enc.split(",") == values
