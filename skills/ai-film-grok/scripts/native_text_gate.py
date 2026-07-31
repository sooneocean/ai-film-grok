"""Fail-closed review gate for provider-generated dialogue clips.

Text-to-video vendors can ignore a negative prompt and burn text into frames.
OCR is not reliable enough to silently clear a delivery, so promotion requires a
recorded frame review instead of trusting the provider or a prompt.
"""

from __future__ import annotations

from typing import Any

_CAPTION_OWNERS = {"ffmpeg", "hyperframes"}


def validate_native_text_review(review: dict[str, Any]) -> dict[str, Any]:
    """Return a structured approval or rejection for one native dialogue clip."""
    missing = [key for key in ("clip_sha256", "sampled_frames") if not review.get(key)]
    if "unexpected_visual_text_detected" not in review:
        missing.append("unexpected_visual_text_detected")
    if missing:
        return {"ok": False, "reason": "NATIVE_TEXT_REVIEW_INCOMPLETE", "missing": missing}
    if review.get("unexpected_visual_text_detected") is not False:
        return {"ok": False, "reason": "PROVIDER_VISUAL_TEXT_REJECTED"}
    if review.get("native_audio_dialogue_matches_expected") is not True:
        return {"ok": False, "reason": "NATIVE_DIALOGUE_MISMATCH"}
    if review.get("mouth_audio_sync_approved") is not True:
        return {"ok": False, "reason": "NATIVE_MOUTH_SYNC_REJECTED"}
    caption_owner = review.get("caption_owner")
    if caption_owner not in _CAPTION_OWNERS:
        return {
            "ok": False,
            "reason": "FINAL_CAPTION_OWNER_INVALID",
            "allowed": sorted(_CAPTION_OWNERS),
        }
    return {"ok": True, "status": "approved", "caption_owner": caption_owner}
