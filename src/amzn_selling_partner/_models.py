import pydantic

__all__ = ["BaseModel"]


class BaseModel(pydantic.BaseModel):
    """Matches pydantic v1's default of silently ignoring unknown fields (important for
    forward-compatibility with SP-API responses); subclasses opt into `extra="forbid"`
    individually where the original v1 model did."""

    model_config = pydantic.ConfigDict(extra="ignore", defer_build=True)
