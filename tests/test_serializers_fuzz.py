"""Hypothesis fuzzing of the parameter encoding: our stringification (petstore_sdk._http) + httpx2's URL encoding."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote

import httpx2
from hypothesis import given, settings
from hypothesis import strategies as st
from petstore_sdk._http import HttpClient, joined, path_segment, scalar

text = st.text(min_size=0, max_size=30)
scalars = st.one_of(text, st.integers(), st.booleans(), st.floats(allow_nan=False, allow_infinity=False))

_client = HttpClient(base_url="https://h", transport=httpx2.MockTransport(lambda r: httpx2.Response(200)))


def encode(params: dict[str, object]) -> str:
    """The query string httpx2 puts on the wire for ``params``."""
    request = _client._build(
        "GET", "/p", params=params, headers=None, json=None, data=None, files=None, content=None, content_type=None, options=None
    )
    return request.url.query.decode()


@given(name=st.from_regex(r"[A-Za-z][A-Za-z0-9_-]{0,10}", fullmatch=True), value=scalars)
@settings(max_examples=200)
def test_query_scalar_roundtrip(name: str, value: object) -> None:
    assert parse_qs(encode({name: value}), keep_blank_values=True) == {name: [scalar(value)]}


@given(name=st.from_regex(r"[A-Za-z][A-Za-z0-9_]{0,10}", fullmatch=True), values=st.lists(text, min_size=1, max_size=5))
@settings(max_examples=200)
def test_query_array_explode_roundtrip(name: str, values: list[str]) -> None:
    assert parse_qs(encode({name: values}), keep_blank_values=True) == {name: values}


@given(values=st.lists(text, min_size=1, max_size=5))
@settings(max_examples=200)
def test_query_array_csv_roundtrip(values: list[str]) -> None:
    assert parse_qs(encode({"k": joined(values, ",")}), keep_blank_values=True) == {"k": [",".join(values)]}


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
