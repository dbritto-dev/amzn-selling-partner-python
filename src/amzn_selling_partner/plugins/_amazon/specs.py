"""Locating and naming the pinned Amazon model files (generator inputs; used
at run time only by the sandbox runner and the tests)."""

from __future__ import annotations

import os
import pathlib
import re

from ...runtime._naming import snake_case

_HERE = pathlib.Path(__file__).resolve().parent
_VERSION_SUFFIX = re.compile(r"(?:[_-]|(?<=[a-z])V)(?P<v>\d{4}-\d{2}-\d{2}|\d+)$")

# stem -> version for files whose stem carries no version (mirrors codegen/src/amazon.ts)
UNVERSIONED = {
    "fbaInbound": "v1",
    "fbaInventory": "v1",
    "messaging": "v1",
    "notifications": "v1",
    "sales": "v1",
    "sellers": "v1",
    "services": "v1",
    "shipping": "v1",
    "solicitations": "v1",
    "vendorInvoices": "v1",
    "vendorOrders": "v1",
    "vendorShipments": "v1",
    "vendorTransactionStatus": "v1",
}


def api_naming(path: pathlib.Path) -> tuple[str, str] | None:
    """``orders_2021-08-01.json`` -> ``("orders", "v2021_08_01")``; ``None`` when the
    stem carries no version and is not in ``UNVERSIONED``."""
    stem = path.stem
    m = _VERSION_SUFFIX.search(stem)
    if m:
        return snake_case(stem[: m.start()]), "v" + m.group("v").replace("-", "_")
    version = UNVERSIONED.get(stem)
    if version is None:
        return None
    return snake_case(stem), version


def spec_files(root: pathlib.Path) -> list[pathlib.Path]:
    if root.is_file():
        return [root]
    models = root / "models" if (root / "models").is_dir() else root
    return sorted(models.glob("**/*.json"))


def default_spec_dir() -> pathlib.Path:
    """The submodule ``models`` directory (or ``AMZN_SELLING_PARTNER_MODELS``)."""
    env = os.environ.get("AMZN_SELLING_PARTNER_MODELS")
    candidates = [pathlib.Path(env)] if env else []
    candidates.append(_HERE.parents[3] / "spec" / "selling-partner-api-models" / "models")
    for c in candidates:
        if c.is_dir() and any(c.glob("*/*.json")):
            return c
    raise FileNotFoundError(
        "Amazon SP-API models not found. Check out the git submodule "
        "(git submodule update --init) or set AMZN_SELLING_PARTNER_MODELS to the models directory."
    )


def default_schema_dir() -> pathlib.Path:
    env = os.environ.get("AMZN_SELLING_PARTNER_SCHEMAS")
    candidates = [pathlib.Path(env)] if env else []
    candidates.append(_HERE.parents[3] / "spec" / "selling-partner-api-models" / "schemas")
    for c in candidates:
        if (c / "notifications").is_dir():
            return c
    raise FileNotFoundError("Amazon SP-API schemas not found (git submodule update --init, or set AMZN_SELLING_PARTNER_SCHEMAS).")


def spec_path(api: str, version: str, root: pathlib.Path | None = None) -> pathlib.Path:
    """The model file behind ``client.<api>.<version>``."""
    for path in spec_files(root or default_spec_dir()):
        named = api_naming(path)
        if named == (api, version):
            return path
    raise KeyError(f"{api}.{version}")


__all__ = ["UNVERSIONED", "api_naming", "default_schema_dir", "default_spec_dir", "spec_files", "spec_path"]
