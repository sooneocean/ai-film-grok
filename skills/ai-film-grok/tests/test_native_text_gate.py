from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from native_text_gate import validate_native_text_review  # noqa: E402


def _approved_review() -> dict[str, object]:
    return {
        "clip_sha256": "a" * 64,
        "sampled_frames": ["frame-001.jpg", "frame-024.jpg"],
        "unexpected_visual_text_detected": False,
        "native_audio_dialogue_matches_expected": True,
        "mouth_audio_sync_approved": True,
        "caption_owner": "ffmpeg",
    }


def test_native_text_gate_approves_only_a_reviewed_clean_clip() -> None:
    assert validate_native_text_review(_approved_review())["ok"] is True


def test_native_text_gate_rejects_provider_burned_text() -> None:
    review = _approved_review()
    review["unexpected_visual_text_detected"] = True
    assert validate_native_text_review(review)["reason"] == "PROVIDER_VISUAL_TEXT_REJECTED"


def test_native_text_gate_requires_a_single_final_caption_owner() -> None:
    review = _approved_review()
    review["caption_owner"] = "provider"
    assert validate_native_text_review(review)["reason"] == "FINAL_CAPTION_OWNER_INVALID"
