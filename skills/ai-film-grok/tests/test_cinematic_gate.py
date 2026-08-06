"""Wave ε · composite cinematic-gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cinematic_gate import (  # noqa: E402
    CinematicGateError,
    assert_cinematic_gate_for_export,
    run_cinematic_gate,
)


def test_skip_escape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_SKIP_CINEMATIC_GATE", "1")
    rep = run_cinematic_gate(tmp_path, write=True)
    assert rep["ok"] is True
    assert rep.get("skipped") is True
    monkeypatch.delenv("AIFILM_SKIP_CINEMATIC_GATE", raising=False)


def test_gate_writes_receipt(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"clips": {}, "gates": {"clips_complete": False}}),
        encoding="utf-8",
    )
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "vo_mode": "storyteller",
                "dramatic_meaning_strict": False,
                # shot present without approved clip → inventory hard red
                "scenes": [{"shots": [{"id": "s1", "dsl": {"motion": "walks"}}]}],
            }
        ),
        encoding="utf-8",
    )
    rep = run_cinematic_gate(
        tmp_path,
        write=True,
        skip_variety=True,
        skip_five_track=True,
    )
    assert (tmp_path / "receipts" / "cinematic-gate.json").is_file()
    assert "steps" in rep
    inv = next(s for s in rep["steps"] if s["id"] == "inventory")
    assert inv["ok"] is False
    assert rep["ok"] is False


def test_true_video_step_flags_still(tmp_path: Path) -> None:
    still = tmp_path / "clips" / "s1.png"
    still.parent.mkdir(parents=True)
    still.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {
                "clips": {
                    "s1": {
                        "status": "approved",
                        "path": str(still),
                        "source_endpoint": "image_to_video",
                        "identity_approved": True,
                        "motion_approved": True,
                        "review_note": "x",
                    }
                },
                "gates": {"clips_complete": True},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "vo_mode": "storyteller",
                "dramatic_meaning_strict": False,
                "scenes": [{"shots": [{"id": "s1", "dsl": {"motion": "walks"}}]}],
            }
        ),
        encoding="utf-8",
    )
    rep = run_cinematic_gate(tmp_path, write=False, skip_variety=True, skip_five_track=True)
    tv = next(s for s in rep["steps"] if s["id"] == "true_video")
    assert tv["ok"] is False


def test_assert_export_blocks_when_red(tmp_path: Path) -> None:
    (tmp_path / "receipts").mkdir(parents=True)
    (tmp_path / "receipts" / "cinematic-gate.json").write_text(
        json.dumps({"ok": False, "blocked_by": "inventory"}),
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"clips": {}, "gates": {}}), encoding="utf-8"
    )
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "vo_mode": "storyteller",
                "dramatic_meaning_strict": False,
                "scenes": [{"shots": [{"id": "s1", "dsl": {"motion": "walks"}}]}],
            }
        ),
        encoding="utf-8",
    )
    # re-run still red: shot without approved clip
    with pytest.raises(CinematicGateError):
        assert_cinematic_gate_for_export(tmp_path)


def test_assert_export_ok_when_green(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_SKIP_CINEMATIC_GATE", "1")
    rep = assert_cinematic_gate_for_export(tmp_path)
    assert rep["ok"] is True
    monkeypatch.delenv("AIFILM_SKIP_CINEMATIC_GATE", raising=False)
