"""Copy the pinned Amazon models and schemas into the package for distribution.

The git repository keeps the specs only in the submodule; the package looks
for them first under ``spapi/plugins/_amazon/{models,schemas}`` (what a built
wheel ships) and falls back to the submodule during development.

    python scripts/sync_specs.py          # copy (run before `uv build`)
    python scripts/sync_specs.py --clean  # remove the copies
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBMODULE = ROOT / "spec" / "selling-partner-api-models"
TARGET = ROOT / "src" / "spapi" / "plugins" / "_amazon"


def sync() -> int:
    if not (SUBMODULE / "models").is_dir():
        print("submodule not checked out: git submodule update --init", file=sys.stderr)
        return 1
    copied = 0
    for name in ("models", "schemas"):
        dest = TARGET / name
        if dest.is_symlink() or dest.exists():
            dest.unlink() if dest.is_symlink() else shutil.rmtree(dest)
        for src in sorted((SUBMODULE / name).rglob("*")):
            if src.is_file() and src.suffix == ".json" and not src.name.endswith(".example.json"):
                rel = src.relative_to(SUBMODULE / name)
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, out)
                copied += 1
    (TARGET / "PINNED_COMMIT").write_text((ROOT / "spec" / "PINNED_COMMIT").read_text())
    print(f"copied {copied} spec files into {TARGET.relative_to(ROOT)}")
    return 0


def clean() -> int:
    for name in ("models", "schemas"):
        dest = TARGET / name
        if dest.is_dir() and not dest.is_symlink():
            shutil.rmtree(dest)
    (TARGET / "PINNED_COMMIT").unlink(missing_ok=True)
    print("removed packaged spec copies")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    sys.exit(clean() if args.clean else sync())
