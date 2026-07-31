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
    audit = review.get("visual_text_audit")
    if not isinstance(audit, dict):
        return {"ok": False, "reason": "VISUAL_TEXT_AUDIT_REQUIRED"}
    if audit.get("kind") != "visual-text-audit" or audit.get("status") != "clean":
        return {"ok": False, "reason": "PROVIDER_VISUAL_TEXT_REJECTED"}
    if (audit.get("clip") or {}).get("sha256") != review.get("clip_sha256"):
        return {"ok": False, "reason": "VISUAL_TEXT_AUDIT_STALE"}
    if review.get("native_audio_dialogue_matches_expected") is not True:
        return {"ok": False, "reason": "NATIVE_DIALOGUE_MISMATCH"}
    if review.get("mouth_audio_sync_approved") is not True:
        return {"ok": False, "reason": "NATIVE_MOUTH_SYNC_REJECTED"}
    expected_duration = review.get("expected_duration_sec")
    native_duration = review.get("native_duration_sec")
    if expected_duration is not None or native_duration is not None:
        if not isinstance(expected_duration, (int, float)) or not isinstance(
            native_duration, (int, float)
        ):
            return {"ok": False, "reason": "NATIVE_DURATION_REVIEW_INCOMPLETE"}
        if abs(float(expected_duration) - float(native_duration)) > 0.5:
            return {
                "ok": False,
                "reason": "NATIVE_DURATION_MISMATCH",
                "expected_duration_sec": expected_duration,
                "native_duration_sec": native_duration,
            }
    caption_owner = review.get("caption_owner")
    if caption_owner not in _CAPTION_OWNERS:
        return {
            "ok": False,
            "reason": "FINAL_CAPTION_OWNER_INVALID",
            "allowed": sorted(_CAPTION_OWNERS),
        }
    return {"ok": True, "status": "approved", "caption_owner": caption_owner}
