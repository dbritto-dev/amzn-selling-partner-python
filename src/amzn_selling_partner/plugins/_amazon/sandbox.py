"""Normalise the sandbox examples embedded in the Amazon models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...spec._jsonutil import as_list, as_object, obj
from ...spec.ir import Operation


@dataclass(slots=True, frozen=True, kw_only=True)
class SandboxExample:
    status: int
    parameters: dict[str, Any] = field(default_factory=dict[str, Any])  # wire parameter name -> value
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
        static = obj(resp.extensions, "x-amzn-api-sandbox")
        entries: list[Any]
        source = "x-amzn-api-sandbox"
        if isinstance(static.get("static"), list):
            entries = as_list(static.get("static"))
        elif isinstance(resp.extensions.get("x-amazon-spds-sandbox-behaviors"), list):
            entries = as_list(resp.extensions.get("x-amazon-spds-sandbox-behaviors"))
            source = "x-amazon-spds-sandbox-behaviors"
        else:
            entries = []
        for raw_entry in entries:
            entry = as_object(raw_entry)
            if entry is None:
                continue
            request = obj(entry, "request")
            params: dict[str, Any] = {}
            body: Any = None
            has_body = False
            for name, spec in obj(request, "parameters").items():
                spec_obj = as_object(spec)
                value: Any = spec_obj["value"] if spec_obj is not None and "value" in spec_obj else spec
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
    return "dynamic" in obj(op.extensions, "x-amzn-api-sandbox")


__all__ = ["SandboxExample", "is_dynamic_sandbox", "sandbox_examples"]
