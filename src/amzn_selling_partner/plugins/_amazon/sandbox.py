"""Normalise the sandbox examples embedded in the Amazon model files (raw JSON)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast


@dataclass(slots=True, frozen=True, kw_only=True)
class SandboxExample:
    status: int
    parameters: dict[str, Any] = field(default_factory=dict[str, Any])  # wire parameter name -> value
    body: Any = None
    has_body: bool = False
    response: Any = None
    has_response: bool = False
    source: str = "x-amzn-api-sandbox"


def _obj(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, Mapping) else {}


def sandbox_examples(raw_op: Mapping[str, Any]) -> list[SandboxExample]:
    """Static request/response pairs of one raw operation object, from
    ``responses.<code>.x-amzn-api-sandbox.static[]`` and the ``vendorShipments``
    variant ``x-amazon-spds-sandbox-behaviors``."""
    out: list[SandboxExample] = []
    for code, resp in _obj(raw_op.get("responses")).items():
        try:
            status = int(code)
        except ValueError:
            continue
        resp_obj = _obj(resp)
        static = _obj(resp_obj.get("x-amzn-api-sandbox"))
        entries: list[Any]
        source = "x-amzn-api-sandbox"
        if isinstance(static.get("static"), list):
            entries = cast(list[Any], static["static"])
        elif isinstance(resp_obj.get("x-amazon-spds-sandbox-behaviors"), list):
            entries = cast(list[Any], resp_obj["x-amazon-spds-sandbox-behaviors"])
            source = "x-amazon-spds-sandbox-behaviors"
        else:
            entries = []
        for raw_entry in entries:
            entry = _obj(raw_entry)
            if not entry:
                continue
            request = _obj(entry.get("request"))
            params: dict[str, Any] = {}
            body: Any = None
            has_body = False
            for name, spec in _obj(request.get("parameters")).items():
                spec_obj = _obj(spec)
                value: Any = spec_obj["value"] if "value" in spec_obj else spec
                if name == "body":
                    body, has_body = value, True
                else:
                    params[str(name)] = value
            out.append(
                SandboxExample(
                    status=status,
                    parameters=params,
                    body=body,
                    has_body=has_body,
                    response=entry.get("response"),
                    has_response="response" in entry,
                    source=source,
                )
            )
    return out


def is_dynamic_sandbox(raw_op: Mapping[str, Any]) -> bool:
    return "dynamic" in _obj(raw_op.get("x-amzn-api-sandbox"))


__all__ = ["SandboxExample", "is_dynamic_sandbox", "sandbox_examples"]
