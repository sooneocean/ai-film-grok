#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_DIR="$ROOT_DIR/skills/ai-film-grok"
AIFILM="$SKILL_DIR/scripts/aifilm"
PY="${PYTHON:-python3}"

echo "=== [1/6] Secret scan (mirrors CI) ==="
"$PY" "$ROOT_DIR/scripts/secret_scan.py"

echo "=== [2/6] Grok Plugin Validation ==="
grok plugin validate "$ROOT_DIR"

echo "=== [3/6] Ruff Lint & Format Check ==="
ruff check "$SKILL_DIR/scripts/"
ruff format --check "$SKILL_DIR/scripts/"

echo "=== [4/6] Aifilm Doctor Diagnosis ==="
# Local doctor stays strict (no AIFILM_CI) — this machine generated runtime-lock.json,
# so version drift should not be tolerated here. CI relaxes this via AIFILM_CI=1.
env -u PYTHONPATH "$AIFILM" doctor

echo "=== [5/6] Pytest (Fast Path) ==="
# Drop host-agent PYTHONPATH so package pins match aifilm's clean runtime.
(cd "$SKILL_DIR" && env -u PYTHONPATH AIFILM_CI=1 "$PY" -m pytest tests/ -q --tb=line -m "not slow")

echo "=== [6/6] Hotpath fail-closed contracts (mirrors CI hotpath job) ==="
(cd "$SKILL_DIR" && env -u PYTHONPATH AIFILM_CI=1 "$PY" -m pytest tests/ -q --tb=line -m "hotpath and not slow")

echo "=== All checks passed successfully! ==="
