from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from native_text_gate import validate_native_text_review  # noqa: E402


def _review() -> dict[str, object]:
    return {
        "clip_sha256": "a" * 64,
        "sampled_frames": ["frames/0001.png"],
        "unexpected_visual_text_detected": False,
        "visual_text_audit": {
            "kind": "visual-text-audit",
            "status": "clean",
            "clip": {"sha256": "a" * 64},
        },
        "native_audio_dialogue_matches_expected": True,
        "mouth_audio_sync_approved": True,
        "caption_owner": "ffmpeg",
    }


def test_native_audio_review_accepts_measured_matching_duration() -> None:
    review = _review() | {"expected_duration_sec": 3.0, "native_duration_sec": 3.4}
    assert validate_native_text_review(review)["ok"] is True


def test_native_audio_review_rejects_duration_mismatch() -> None:
    review = _review() | {"expected_duration_sec": 3.0, "native_duration_sec": 3.6}
    assert validate_native_text_review(review)["reason"] == "NATIVE_DURATION_MISMATCH"


def test_native_audio_review_requires_current_automatic_text_audit() -> None:
    review = _review()
    del review["visual_text_audit"]
    assert validate_native_text_review(review)["reason"] == "VISUAL_TEXT_AUDIT_REQUIRED"
    review = _review()
    review["visual_text_audit"]["clip"]["sha256"] = "b" * 64
    assert validate_native_text_review(review)["reason"] == "VISUAL_TEXT_AUDIT_STALE"
