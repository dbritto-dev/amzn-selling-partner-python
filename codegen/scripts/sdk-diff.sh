#!/usr/bin/env bash
# Diff two versions of the spec (`oagen diff`): added/removed operations,
# parameter and schema changes.
#
#   npm run sdk:diff                       # last committed spec/open-api-spec.yaml -> working tree
#   npm run sdk:diff -- --old <ref>        # e.g. --old main, --old HEAD~3
#   npm run sdk:diff -- --old a.yaml --new b.yaml
set -euo pipefail

SPEC="spec/open-api-spec.yaml"
OLD="HEAD"
NEW="$SPEC"
TMP=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --old) OLD="$2"; shift 2 ;;
    --new) NEW="$2"; shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

cleanup() { [[ -n "$TMP" ]] && rm -f "$TMP"; }
trap cleanup EXIT

# `--old` is a file, or a git ref whose copy of the spec is checked out to a temp file.
if [[ ! -f "$OLD" ]]; then
  TMP="$(mktemp "${TMPDIR:-/tmp}/oagen-spec-old.XXXXXX.yaml")"
  git show "${OLD}:codegen/${SPEC}" > "$TMP"
  OLD="$TMP"
fi

exec npx oagen diff --old "$OLD" --new "$NEW"
