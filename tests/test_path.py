import pytest

from amzn_selling_partner._path import path_template


def test_interpolates_placeholder() -> None:
    assert path_template("reports/{report_id}", report_id="abc") == "reports/abc"


def test_interpolates_multiple_placeholders() -> None:
    assert path_template("a/{x}/b/{y}", x="1", y="2") == "a/1/b/2"


def test_percent_encodes_unsafe_characters() -> None:
    # A slash in the value must not be allowed to introduce an extra path segment.
    assert path_template("reports/{report_id}", report_id="a/b") == "reports/a%2Fb"
    assert path_template("reports/{report_id}", report_id="a b") == "reports/a%20b"


def test_missing_placeholder_value_raises_key_error() -> None:
    with pytest.raises(KeyError):
        path_template("reports/{report_id}", other="x")


@pytest.mark.parametrize("malicious_value", ["..", "."])
def test_rejects_dot_segment_path_traversal(malicious_value: str) -> None:
    # Dots are in urllib.parse.quote's default "always safe" set, so quoting alone does
    # NOT neutralize "..": the explicit post-interpolation segment check is what protects
    # against a caller-supplied id redirecting the request via `../` traversal.
    with pytest.raises(ValueError, match="dot-segment"):
        path_template("reports/{report_id}", report_id=malicious_value)


def test_percent_encoded_dot_segment_value_is_harmless() -> None:
    # A value that is literally the text "%2e%2e" is not a traversal attempt: quote()
    # escapes the '%' itself (to %25), so it can never produce a raw dot-segment via
    # interpolation -- it's just an oddly-named, otherwise-inert path segment.
    assert path_template("reports/{report_id}", report_id="%2e%2e") == "reports/%252e%252e"


def test_rejects_dot_segment_in_the_middle_of_the_path() -> None:
    with pytest.raises(ValueError, match="dot-segment"):
        path_template("reports/{report_id}/documents", report_id="..")


def test_allows_dots_within_a_segment() -> None:
    # A value merely containing dots (not equal to a bare dot-segment) is fine.
    assert path_template("reports/{report_id}", report_id="report.v1") == "reports/report.v1"
