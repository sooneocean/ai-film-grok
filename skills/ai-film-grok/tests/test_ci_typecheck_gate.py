"""D7.2 · CI must keep typecheck job aligned with make type."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CI = ROOT / ".github" / "workflows" / "ci.yml"
MAKE = ROOT / "Makefile"


def test_ci_has_typecheck_job() -> None:
    text = CI.read_text(encoding="utf-8")
    assert "typecheck:" in text
    assert "make type" in text
    assert "needs.typecheck.result" in text or "needs: [validate-core, hotpath, test-full, console, typecheck]" in text


def test_make_type_lists_util_seed() -> None:
    text = MAKE.read_text(encoding="utf-8")
    assert "scripts/util/errors.py" in text
    assert "scripts/util/security_policy.py" in text
    assert "scripts/core/gates.py" in text
    assert "scripts/core/media_ops.py" in text
