"""Normalise the sandbox examples embedded in the Amazon models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ...spec.ir import Operation


@dataclass(slots=True, frozen=True, kw_only=True)
class SandboxExample:
    status: int
    parameters: dict[str, Any] = field(default_factory=dict)  # wire parameter name -> value
    body: Any = None
    has_body: bool = False
    response: Any = None
    has_response: bool = False
    source: str = "x-amzn-api-sandbox"


def sandbox_examples(op: Operation) -> list[SandboxExample]:
    """Static request/response pairs for an operation, from
    ``responses.<code>.x-amzn-api-sandbox.static[]`` and the ``vendorShipments``
    variant ``x-amazon-spds-sandbox-behaviors``."""
    out: list[SandboxExample] = []
    for code, resp in op.responses.items():
        try:
            status = int(code)
        except ValueError:
            continue
        static = resp.extensions.get("x-amzn-api-sandbox", {})
        entries: list[Any] = []
        source = "x-amzn-api-sandbox"
        if isinstance(static, Mapping) and isinstance(static.get("static"), list):
            entries = list(static["static"])
        elif isinstance(resp.extensions.get("x-amazon-spds-sandbox-behaviors"), list):
            entries = list(resp.extensions["x-amazon-spds-sandbox-behaviors"])
            source = "x-amazon-spds-sandbox-behaviors"
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            request = entry.get("request") or {}
            params_raw = request.get("parameters") or {}
            params: dict[str, Any] = {}
            body: Any = None
            has_body = False
            for name, spec in params_raw.items():
                value = spec.get("value") if isinstance(spec, Mapping) and "value" in spec else spec
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


def is_dynamic_sandbox(op: Operation) -> bool:
    ext = op.extensions.get("x-amzn-api-sandbox")
    return isinstance(ext, Mapping) and "dynamic" in ext


__all__ = ["SandboxExample", "is_dynamic_sandbox", "sandbox_examples"]
