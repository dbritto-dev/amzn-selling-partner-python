"""Helpers shared by the compatibility resources."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from ._naming import param_name
from .sdk.resources import OPERATIONS


def query_kwargs(query: BaseModel | dict[str, Any] | None) -> dict[str, Any]:
    """Old ``*Query`` models used the wire parameter names as fields; map
    them to the snake_case keyword arguments of the generated methods."""
    if query is None:
        return {}
    data = query.model_dump(exclude_none=True, by_alias=True) if isinstance(query, BaseModel) else dict(query)
    return {param_name(k): v for k, v in data.items()}


def to_body(data: Any) -> Any:
    if isinstance(data, BaseModel):
        return data.model_dump(exclude_none=True, by_alias=True, mode="json")
    return data


def require_str(value: object, name: str) -> str:
    """The 0.1.x clients validated ids at runtime; keep that contract."""
    if not value or not isinstance(value, str):
        raise ValueError(f"{name} must be a string present but found `{value}`")
    return value


def operation(client: Any, module: str, operation_id: str) -> Any:
    """The generated method of ``operationId`` on ``client.<module>`` (looked up
    through the resources registry, so Amazon's operation names stay the key)."""
    method, *_rest = OPERATIONS[f"{module}.{operation_id}"]
    return getattr(getattr(client, module), method)
