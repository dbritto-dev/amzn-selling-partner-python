"""API attribute names for the Amazon model files (see docs/PLAN.md §3)."""

from __future__ import annotations

import pathlib
import re

from ...compile.naming import snake_case

_VERSION_SUFFIX = re.compile(r"(?:[_-]|(?<=[a-z])V)(?P<v>\d{4}-\d{2}-\d{2}|\d+)$")

# stem -> info.version for files whose stem carries no version
_UNVERSIONED = {
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

ALIASES = {
    "invoices": "invoices_api_model",
    "product_type_definitions": "definitions_product_types",
    "fba_inbound_eligibility": "fba_inbound",
    "amazon_warehousing_and_distribution": "awd",
    "application_integrations": "app_integrations",
}


def api_naming(path: pathlib.Path) -> tuple[str, str] | None:
    stem = path.stem
    m = _VERSION_SUFFIX.search(stem)
    if m:
        return snake_case(stem[: m.start()]), "v" + m.group("v").replace("-", "_")
    version = _UNVERSIONED.get(stem)
    if version is None:
        return None
    return snake_case(stem), version


def spec_files(root: pathlib.Path) -> list[pathlib.Path]:
    if root.is_file():
        return [root]
    models = root / "models" if (root / "models").is_dir() else root
    return sorted(models.glob("**/*.json"))


__all__ = ["ALIASES", "api_naming", "spec_files"]
