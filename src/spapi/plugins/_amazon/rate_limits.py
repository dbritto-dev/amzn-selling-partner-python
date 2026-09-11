"""Parse the "Rate (requests per second) | Burst" usage-plan tables."""

from __future__ import annotations

import logging
import re

from ...runtime._throttle import RateLimit
from ...spec.ir import Document, Operation

log = logging.getLogger("spapi.plugins.amazon.rate_limits")

# | Rate (requests per second) | Burst |
# | ---- | ---- |
# | 0.0167 | 20 |
_TWO_COL = re.compile(
    r"\|\s*Rate\s*\(requests per second\)\s*\|\s*Burst\s*\|\s*\n\s*\|[\s:-]+\|[\s:-]+\|\s*\n\s*\|\s*(?P<rate>[0-9]*\.?[0-9]+)\s*\|\s*(?P<burst>[0-9]+)\s*\|",
    re.IGNORECASE,
)
# | Plan type | Rate (requests per second) | Burst |
# | ---- | ---- | ---- |
# |Default| 5 | 10 |
_THREE_COL = re.compile(
    r"\|\s*Plan type\s*\|\s*Rate\s*\(requests per second\)\s*\|\s*Burst\s*\|\s*\n\s*\|[\s:-]+\|[\s:-]+\|[\s:-]+\|\s*\n(?:.*\n)*?\s*\|\s*Default\s*\|\s*(?P<rate>[0-9]*\.?[0-9]+)\s*\|\s*(?P<burst>[0-9]+)\s*\|",
    re.IGNORECASE,
)


def parse_rate_limit(description: str | None) -> RateLimit | None:
    """Return the default rate limit from an operation description, or ``None``
    when there is no table or the table cannot be parsed (never guesses)."""
    if not description:
        return None
    m = _TWO_COL.search(description) or _THREE_COL.search(description)
    if m is None:
        return None
    try:
        return RateLimit(rate=float(m.group("rate")), burst=int(m.group("burst")))
    except ValueError:
        return None


def annotate_rate_limits(document: Document, key: str) -> tuple[Document, list[str]]:
    """Attach ``rate_limit`` annotations; returns the document and the ids of
    operations whose description has no parseable table."""
    unparsed: list[str] = []
    ops: list[Operation] = []
    for op in document.operations:
        limit = parse_rate_limit(op.description)
        if limit is None:
            unparsed.append(op.operation_id)
            log.info("%s.%s: no parseable rate-limit table in description", key, op.operation_id)
            ops.append(op)
        else:
            ops.append(op.annotated(rate_limit=limit))
    return document.with_operations(tuple(ops)), unparsed


__all__ = ["annotate_rate_limits", "parse_rate_limit"]
