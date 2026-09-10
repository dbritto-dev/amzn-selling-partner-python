"""Turn IR into fast callables: pydantic models, compiled operations, resources."""

from .models import ModelNamespace, build_models
from .operations import CompiledOp, compile_operation, compile_operations, detect_pagination
from .resources import ResourcePair, build_resource, build_resources

__all__ = [
    "CompiledOp",
    "ModelNamespace",
    "ResourcePair",
    "build_models",
    "build_resource",
    "build_resources",
    "compile_operation",
    "compile_operations",
    "detect_pagination",
]
