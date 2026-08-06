#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_DIR="$ROOT_DIR/skills/ai-film-grok"
AIFILM="$SKILL_DIR/scripts/aifilm"
PY="${PYTHON:-python3}"

echo "=== [1/7] Secret scan (mirrors CI) ==="
"$PY" "$ROOT_DIR/scripts/secret_scan.py"

echo "=== [2/7] Grok Plugin Validation ==="
grok plugin validate "$ROOT_DIR"

echo "=== [3/7] Ruff Lint & Format Check ==="
ruff check "$SKILL_DIR/scripts/"
ruff format --check "$SKILL_DIR/scripts/"

echo "=== [4/7] Aifilm Doctor Diagnosis ==="
# Local doctor stays strict (no AIFILM_CI) — this machine generated runtime-lock.json,
# so version drift should not be tolerated here. CI relaxes this via AIFILM_CI=1.
env -u PYTHONPATH "$AIFILM" doctor

echo "=== [5/7] Pytest + Coverage (Fast Path, mirrors CI 58% floor) ==="
# Drop host-agent PYTHONPATH so package pins match aifilm's clean runtime.
(cd "$SKILL_DIR" && env -u PYTHONPATH AIFILM_CI=1 "$PY" -m coverage run -m pytest tests/ -q --tb=line -m "not slow")

echo "=== [6/7] Hotpath fail-closed contracts (mirrors CI hotpath job) ==="
(cd "$SKILL_DIR" && env -u PYTHONPATH AIFILM_CI=1 "$PY" -m pytest tests/ -q --tb=line -m "hotpath and not slow")

echo "=== [7/7] Coverage gate (mirrors CI: 58% floor + per-file floors) ==="
(cd "$SKILL_DIR" && env -u PYTHONPATH AIFILM_CI=1 "$PY" -m coverage report --fail-under=58 \
  && "$PY" -m coverage json -o coverage.json \
  && "$PY" - <<'PY'
import json
data = json.load(open("coverage.json"))
files = data.get("files", {})
floors = {"media_qa.py": 45, "quality_evidence.py": 80, "continuity.py": 85}
for name, floor in floors.items():
    row = next((v for k, v in files.items() if k.endswith(f"scripts/{name}")), None)
    assert row is not None, f"coverage row missing: {name}"
    actual = row["summary"]["percent_covered"]
    assert actual >= floor, f"{name} coverage {actual:.1f}% < {floor}%"
    print(f"coverage floor OK: {name}={actual:.1f}%")
print("coverage gate OK")
PY
)

echo "=== All checks passed successfully! ==="
