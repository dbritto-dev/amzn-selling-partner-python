#!/usr/bin/env bash
# Prove the output runs: the tutorial's tasks API (generated on the fly into
# .build/tasks_sdk) and the committed Amazon SDK, both over httpx2.MockTransport.
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/sdk-generate.sh --spec ../tests/fixtures/tasks-api.yml --namespace TasksClient --output .build/tasks_sdk > /dev/null
cd ..
uv run python codegen/scripts/smoke_tasks.py
echo
uv run python codegen/scripts/smoke.py
