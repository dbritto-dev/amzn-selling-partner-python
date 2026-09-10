"""Naming rule for Amazon SP-API model files -> (api_name, version) pairs.

Kept as a standalone script so the plan/table in docs/PLAN.md and
docs/UPDATING_SPECS.md can be regenerated after a submodule bump:

    python scripts/spec_naming.py            # markdown table
    python scripts/spec_naming.py --check    # exit 1 on collisions
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

MODELS = pathlib.Path(__file__).resolve().parents[1] / "spec/selling-partner-api-models/models"

# file-stem suffixes: "_2021-08-01", "-2022-11-07", "V2022-07-01", "V0", "V1", "V2"
_VERSION_SUFFIX = re.compile(r"(?:[_-]|(?<=[a-z])V)(?P<v>\d{4}-\d{2}-\d{2}|\d+)$|(?<=[a-z])V(?P<n>\d+)$")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

# Friendlier aliases the Amazon plugin adds on top of the mechanical names.
ALIASES = {
    "invoices_api_model": "invoices",
    "definitions_product_types": "product_type_definitions",
    "fba_inbound": "fba_inbound_eligibility",
    "awd": "amazon_warehousing_and_distribution",
    "app_integrations": "application_integrations",
}


def snake(name: str) -> str:
    return _CAMEL.sub("_", name).replace("-", "_").lower()


def api_name_and_version(path: pathlib.Path) -> tuple[str, str]:
    stem = path.stem
    m = _VERSION_SUFFIX.search(stem)
    base = stem[: m.start()] if m else stem
    info_version = json.loads(path.read_text())["info"]["version"]
    version = "v" + info_version.lstrip("vV").replace("-", "_")
    return snake(base), version


def version_key(v: str) -> tuple[int, str]:
    # integer versions (v0, v1, v2) sort before date versions (v2021_08_01)
    body = v[1:]
    return (1, body) if "_" in body else (0, body.zfill(4))


def main(argv: list[str]) -> int:
    rows: dict[str, dict[str, pathlib.Path]] = {}
    for f in sorted(MODELS.glob("**/*.json")):
        name, version = api_name_and_version(f)
        if version in rows.setdefault(name, {}):
            print(f"collision: {name} {version}: {f} and {rows[name][version]}", file=sys.stderr)
            return 1
        rows[name][version] = f
    if "--check" in argv:
        print(f"ok: {len(rows)} apis, {sum(len(v) for v in rows.values())} spec files")
        return 0
    print("| `client.<api>` | alias | versions (`latest` first) | spec file(s) |")
    print("|---|---|---|---|")
    for name in sorted(rows):
        versions = sorted(rows[name], key=version_key, reverse=True)
        files = ", ".join(f"`{rows[name][v].relative_to(MODELS)}`" for v in versions)
        alias = f"`{ALIASES[name]}`" if name in ALIASES else ""
        print(f"| `{name}` | {alias} | {', '.join(f'`{v}`' for v in versions)} | {files} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
