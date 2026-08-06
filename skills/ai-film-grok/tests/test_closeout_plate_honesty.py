"""S1.4 · OFFICIAL_FINAL_PLATE never counts as final_complete."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from closeout import closeout_status, plate_delivery_honesty  # noqa: E402


def test_plate_honesty_detects_official_report(tmp_path: Path) -> None:
    rec = tmp_path / "receipts"
    rec.mkdir()
    (rec / "official-final-report.json").write_text(
        json.dumps({"status": "OFFICIAL_PLATE_PLACEHOLDER"}),
        encoding="utf-8",
    )
    # wrong status — not plate
    assert plate_delivery_honesty(tmp_path)["is_official_plate"] is False
    (rec / "official-final-report.json").write_text(
        json.dumps({"status": "OFFICIAL_FINAL_PLATE", "master_lock": False}),
        encoding="utf-8",
    )
    h = plate_delivery_honesty(tmp_path)
    assert h["is_official_plate"] is True
    assert h["master_eligible"] is False


def test_closeout_blocks_final_complete_when_plate_only(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "film_final.mp4").write_bytes(b"fake")
    rec = tmp_path / "receipts"
    rec.mkdir()
    (rec / "official-final-report.json").write_text(
        json.dumps({"status": "OFFICIAL_FINAL_PLATE"}),
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"gates": {"final_complete": True, "desktop_exported": False}}),
        encoding="utf-8",
    )
    st = closeout_status(tmp_path)
    step = next(s for s in st["steps"] if s["id"] == "final_complete")
    assert step["ok"] is False
    assert "OFFICIAL_FINAL_PLATE" in str(step["detail"]) or "plate" in str(step["detail"]).lower()
