#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_DIR="$ROOT_DIR/skills/ai-film-grok"
AIFILM="$SKILL_DIR/scripts/aifilm"

echo "=== [1/4] Grok Plugin Validation ==="
grok plugin validate "$ROOT_DIR"

echo "=== [2/4] Ruff Lint & Format Check ==="
ruff check "$SKILL_DIR/scripts/"
ruff format --check "$SKILL_DIR/scripts/"

echo "=== [3/4] Aifilm Doctor Diagnosis ==="
env -u PYTHONPATH "$AIFILM" doctor

echo "=== [4/4] Pytest (Fast Path) ==="
# Drop host-agent PYTHONPATH so package pins match aifilm's clean runtime.
(cd "$SKILL_DIR" && env -u PYTHONPATH python3 -m pytest tests/ -q --tb=line -m "not slow")

echo "=== All checks passed successfully! ==="
