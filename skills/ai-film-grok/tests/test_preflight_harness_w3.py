"""W3.4 preflight harness: missing root / bare root / minimal report shape."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from preflight import PreflightError, run_preflight


def test_preflight_raises_on_missing_root(tmp_path: Path) -> None:
    missing = tmp_path / "no-such-film"
    with pytest.raises(PreflightError, match="film root missing"):
        run_preflight(missing)


def test_preflight_raises_when_root_is_file(tmp_path: Path) -> None:
    f = tmp_path / "not-a-dir.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(PreflightError, match="film root missing"):
        run_preflight(f)


def test_preflight_bare_root_returns_report_shape(tmp_path: Path) -> None:
    """Empty film dir must not crash (premium soft-read); returns hard/soft lists."""
    report = run_preflight(tmp_path)
    assert isinstance(report, dict)
    assert isinstance(report.get("hard"), list)
    assert isinstance(report.get("soft"), list)
    # No production-book / no premium_vertical → must not throw CREATIVE hard via require
    codes = {item.get("code") for item in report["hard"]}
    assert "CREATIVE_QUALITY_VALIDATION_FAILED" not in codes
    assert "PREPRODUCTION_READINESS_FAILED" not in codes


def test_preflight_minimal_manifest_spec_runs(tmp_path: Path) -> None:
    (tmp_path / "receipts").mkdir()
    (tmp_path / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "gates": {}, "clips": {}, "outputs": {}}),
        encoding="utf-8",
    )
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "title": "w3-harness",
                "vo_mode": "storyteller",
                "scenes": [{"shots": [{"id": "s1", "nar": "短", "duration_sec": 4}]}],
            }
        ),
        encoding="utf-8",
    )
    report = run_preflight(tmp_path)
    assert "hard" in report and "soft" in report
    assert isinstance(report["hard"], list)
