from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cinematic_audit import audit, current_audit, write_audit


def _shot(shot_id: str, *, mode: str, beat: str, duration: float = 3) -> dict:
    return {
        "id": shot_id,
        "beat_id": beat,
        "screen_mode": mode,
        "duration_sec": duration,
        "dramatic_function": "reaction" if mode == "reaction" else "hook",
        "performance_delta": "eyes move to the door"
        if mode == "reaction"
        else "hand opens the door",
        "dsl": {
            "cast": ["hero"],
            "camera": {"shot_size": "close-up" if mode == "reaction" else "medium"},
            "camera_axis": "locked" if mode == "reaction" else "pan_with",
            "motion": "eyes widen and glance back"
            if mode == "reaction"
            else "turn and step toward the door",
            "visible_change": "the door is open",
            "story_beat": "new information arrives",
        },
    }


def test_audit_rejects_dialogue_beat_without_coverage(tmp_path: Path) -> None:
    spec = {"scenes": [{"shots": [_shot("s1", mode="on_camera", beat="b1")]}]}
    report = audit(tmp_path, spec=spec)
    assert not report["ok"]
    assert "DIALOGUE_BEAT_COVERAGE_MISSING" in report["blocking_codes"]


def test_audit_reports_a_stable_code_when_film_spec_is_missing(tmp_path: Path) -> None:
    report = audit(tmp_path, require_authored_contract=True)

    assert report["ok"] is False
    assert report["blocking_codes"] == ["FILM_SPEC_MISSING"]


def test_audit_accepts_dialogue_coverage_and_tracks_receipt_freshness(tmp_path: Path) -> None:
    spec = {
        "scenes": [
            {
                "shots": [
                    _shot("s1", mode="on_camera", beat="b1", duration=8),
                    _shot("s2", mode="reaction", beat="b1", duration=2),
                ]
            }
        ],
        "transition_intents": ["hard"],
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    report = write_audit(tmp_path)
    assert report["ok"], report["issues"]
    assert current_audit(tmp_path)["ok"]
    spec["scenes"][0]["shots"][0]["dsl"]["motion"] = "blink"
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    assert current_audit(tmp_path)["blocking_codes"] == ["CINEMATIC_AUDIT_STALE"]


def test_media_evidence_requires_a_decodable_final_and_approved_clip_records(
    tmp_path: Path,
) -> None:
    spec = {
        "scenes": [
            {
                "shots": [
                    _shot("s1", mode="on_camera", beat="b1", duration=8),
                    _shot("s2", mode="reaction", beat="b1", duration=2),
                ]
            }
        ],
        "transition_intents": ["hard"],
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps({"clips": {"s1": {}}}), encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir()
    (out / "film_final.mp4").write_bytes(b"not-a-video")

    report = audit(tmp_path, require_media_evidence=True)

    assert report["ok"] is False
    assert {"CLIP_EVIDENCE_INVALID", "FINAL_MEDIA_QA_FAILED"} <= set(report["blocking_codes"])


def test_pre_render_audit_does_not_require_a_final_mp4(tmp_path: Path) -> None:
    spec = {"scenes": [{"shots": [_shot("s1", mode="reaction", beat="b1")]}]}

    report = audit(tmp_path, spec=spec)

    assert "FINAL_MEDIA_MISSING" not in report["blocking_codes"]
