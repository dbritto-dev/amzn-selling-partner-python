"""Small value types shared by the compiler and the runtime.

Everything here is deliberately cheap: ``NotGiven`` is a singleton sentinel and
``RequestOptions`` is a frozen, slotted dataclass so that building per-call
options never involves pydantic.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

if TYPE_CHECKING:
    import httpx2

    from ._pagination import Pagination


class NotGiven(enum.Enum):
    """Sentinel for "the caller did not pass this keyword argument".

    Distinct from ``None`` so that ``None`` can be sent explicitly where a spec
    allows ``null``. Implemented as a single-member enum so that type checkers
    can narrow on ``is NOT_GIVEN`` and so that the value pickles.
    """

    NOT_GIVEN = "NOT_GIVEN"

    def __bool__(self) -> Literal[False]:
        return False

    def __repr__(self) -> str:
        return "NOT_GIVEN"


NOT_GIVEN: Final = NotGiven.NOT_GIVEN

type HeaderPairs = tuple[tuple[str, str], ...]


@dataclass(slots=True, frozen=True, kw_only=True)
class RequestOptions:
    """Per-call overrides. The default instance is shared; only callers that
    pass an override pay for constructing a new one."""

    timeout: httpx2.Timeout | float | None = None
    extra_headers: Mapping[str, str] | None = None
    extra_query: Mapping[str, Any] | None = None
    max_retries: int | None = None
    paginate: Pagination | None | NotGiven = NOT_GIVEN
    raw: bool = False
    #: free-form hints for the auth hook (e.g. ``{"rdt": ["buyerInfo"]}`` for
    #: the Amazon plugin); passed to the transport layer as
    #: ``request.extensions["spapi_auth"]``.
    auth: Mapping[str, Any] | None = None


DEFAULT_OPTIONS: Final = RequestOptions()


def merge_headers(base: HeaderPairs, extra: Mapping[str, str] | None) -> HeaderPairs:
    if not extra:
        return base
    return base + tuple(extra.items())
