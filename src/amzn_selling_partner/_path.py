import re
import typing
from urllib.parse import quote

# Matches '.' or '..' where each dot is either literal or percent-encoded (%2e / %2E).
_DOT_SEGMENT_RE = re.compile(r"^(?:\.|%2[eE]){1,2}$")
_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

__all__ = ["path_template"]


def _quote_path_segment(value: str) -> str:
    """Percent-encode `value` for use in a URI path segment (RFC 3986 section 3.3)."""
    return quote(value, safe="!$&'()*+,;=:@")


def path_template(template: str, /, **kwargs: typing.Any) -> str:
    """Interpolate `{name}` placeholders in `template` from keyword arguments,
    percent-encoding each value for safe use in a URL path segment.

    Rejects a resulting path containing a `.`/`..` segment (including percent-encoded
    dot-segments), so a caller-supplied value (e.g. a report or purchase order id) can
    never redirect the request to an unintended endpoint via `../` traversal.

    Raises:
        KeyError: If a placeholder in `template` has no matching keyword argument.
        ValueError: If the interpolated path contains a dot-segment.
    """
    parts = _PLACEHOLDER_RE.split(template)
    for i in range(1, len(parts), 2):
        name = parts[i]
        if name not in kwargs:
            raise KeyError(f"a value for placeholder {{{name}}} was not provided")
        parts[i] = _quote_path_segment(str(kwargs[name]))
    result = "".join(parts)

    for segment in result.split("/"):
        if _DOT_SEGMENT_RE.match(segment):
            raise ValueError(
                f"constructed path {result!r} contains dot-segment {segment!r}, "
                "which is not allowed"
            )

    return result
