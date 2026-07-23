from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audio_visual_alignment import build_audio_visual_alignment  # noqa: E402
from beat_action_evidence import build_beat_action_evidence  # noqa: E402
from editor_cut import build_editor_cut_report  # noqa: E402


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "film"
    (root / "receipts" / "reviews").mkdir(parents=True)
    (root / "clips").mkdir()
    (root / "film-spec.json").write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "id": "scene01",
                        "shots": [
                            {
                                "id": "shot01",
                                "action": "turns toward the door",
                                "content_channels": {
                                    "performance": {"playable_action": "turns toward the door"}
                                },
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return root


def test_beat_action_evidence_blocks_without_approved_timestamp_review(tmp_path: Path) -> None:
    report = build_beat_action_evidence(_root(tmp_path), write=False)
    assert report["ok"] is False
    assert any(item["code"] == "BEAT_ACTION_REVIEW_NOT_APPROVED" for item in report["errors"])


def test_editor_cut_requires_approved_active_media(tmp_path: Path) -> None:
    root = _root(tmp_path)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "clips": {
                    "shot01": {
                        "path": str(root / "clips" / "shot01.mp4"),
                        "status": "approved",
                        "state": "stale",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    report = build_editor_cut_report(root, write=False)
    assert report["ok"] is False
    assert any(item["code"] == "EDITOR_CLIP_NOT_ACTIVE" for item in report["errors"])


def test_audio_visual_alignment_reports_missing_mix_for_timeline(tmp_path: Path) -> None:
    root = _root(tmp_path)
    (root / "timeline.json").write_text(
        json.dumps({"shots": [{"id": "shot01", "duration_sec": 2}]}), encoding="utf-8"
    )
    report = build_audio_visual_alignment(root, write=False)
    assert report["ok"] is False
    assert any(item["code"] == "AUDIO_MIX_REPORT_MISSING" for item in report["errors"])
