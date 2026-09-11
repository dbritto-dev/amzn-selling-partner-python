#!/usr/bin/env bash
# Generate an SDK from the committed spec (the tutorial's `oagen generate` command).
#
#   npm run sdk:generate                                   # Amazon -> ../src/amzn_selling_partner/sdk
#   npm run sdk:generate -- --spec spec/petstore.yaml --output ../tests/petstore_sdk
#   npm run sdk:generate -- --spec ../tests/fixtures/tasks-api.yml --namespace TasksClient --output ../tasks_sdk
set -euo pipefail

SPEC="spec/open-api-spec.yaml"
LANG="python"
NAMESPACE="Client"
OUTPUT="../src/amzn_selling_partner/sdk"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --spec)      SPEC="$2";      shift 2 ;;
    --lang)      LANG="$2";      shift 2 ;;
    --namespace) NAMESPACE="$2"; shift 2 ;;
    --output)    OUTPUT="$2";    shift 2 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ ! -f "$SPEC" ]]; then
  echo "error: spec '$SPEC' not found (run 'npm run spec:build' first)" >&2
  exit 1
fi

# Generating into an existing output directory merges instead of overwriting
# (emitter changes would silently not appear): start from a clean directory.
rm -rf "$OUTPUT"
exec npx oagen generate --lang "$LANG" --spec "$SPEC" --namespace "$NAMESPACE" --output "$OUTPUT"
