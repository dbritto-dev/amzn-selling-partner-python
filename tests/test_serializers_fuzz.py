"""Hypothesis fuzzing of the generated parameter encoders (petstore_sdk._http)."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote

from hypothesis import given, settings
from hypothesis import strategies as st
from petstore_sdk._http import _encode_query, _query_items, joined, path_segment, scalar

text = st.text(min_size=0, max_size=30)
scalars = st.one_of(text, st.integers(), st.booleans(), st.floats(allow_nan=False, allow_infinity=False))


def encode(params: dict[str, object]) -> str:
    return _encode_query(_query_items(params))


@given(name=st.from_regex(r"[A-Za-z][A-Za-z0-9_-]{0,10}", fullmatch=True), value=scalars)
@settings(max_examples=200)
def test_query_scalar_roundtrip(name: str, value: object) -> None:
    assert parse_qs(encode({name: value}), keep_blank_values=True) == {name: [scalar(value)]}


@given(name=st.from_regex(r"[A-Za-z][A-Za-z0-9_]{0,10}", fullmatch=True), values=st.lists(text, min_size=1, max_size=5))
@settings(max_examples=200)
def test_query_array_explode_roundtrip(name: str, values: list[str]) -> None:
    assert parse_qs(encode({name: values}), keep_blank_values=True) == {name: values}


@given(values=st.lists(text.filter(lambda s: "," not in s), min_size=1, max_size=5))
@settings(max_examples=200)
def test_query_array_csv_roundtrip(values: list[str]) -> None:
    enc = encode({"k": joined(values, ",")})
    assert parse_qs(enc, keep_blank_values=True) == {"k": [",".join(values)]}
    assert enc.count(",") == len(values) - 1  # joining commas stay unencoded, commas inside values are encoded


@given(values=st.lists(text, min_size=1, max_size=5), sep=st.sampled_from(["|", " "]))
@settings(max_examples=100)
def test_query_delimited(values: list[str], sep: str) -> None:
    assert parse_qs(encode({"k": joined(values, sep)}), keep_blank_values=True) == {"k": [sep.join(values)]}


@given(value=scalars)
@settings(max_examples=200)
def test_path_scalar_is_single_segment(value: object) -> None:
    enc = path_segment(value)
    assert "/" not in enc and "?" not in enc and "#" not in enc and " " not in enc
    assert unquote(enc) == scalar(value)


@given(value=text)
def test_path_greedy_keeps_slash(value: str) -> None:
    enc = path_segment(value, greedy=True)
    assert unquote(enc) == value
    assert enc.count("/") == value.count("/")
