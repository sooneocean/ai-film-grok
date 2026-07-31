"""Compile the dialogue-first weapon chain into one auditable, no-spend plan."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dialogue_scene_package import validate_dialogue_scene_package
from film_spec import FilmSpecError, validate_film_spec
from util import read_json, utc_now, write_json

_PLAN_NAME = "dialogue-production-plan.json"


def _shots(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(shot.get("dialogue_line_id")): shot
        for scene in spec.get("scenes") or []
        if isinstance(scene, dict)
        for shot in scene.get("shots") or []
        if isinstance(shot, dict) and str(shot.get("dialogue_line_id") or "").strip()
    }


def _stage(
    stage_id: str,
    *,
    line_id: str,
    kind: str,
    tool: str,
    depends_on: list[str],
    evidence_required: list[str],
    activation: str = "always",
) -> dict[str, Any]:
    return {
        "stage_id": stage_id,
        "line_id": line_id,
        "kind": kind,
        "tool": tool,
        "depends_on": depends_on,
        "execution": "manual_verified_only",
        "activation": activation,
        "evidence_required": evidence_required,
    }


def build_dialogue_production_plan(root: Path | str) -> dict[str, Any]:
    """Return the explicit line-keyed dialogue production workflow.

    This deliberately does not submit media work. It makes every required
    operator handoff and receipt visible before a queue is touched.
    """
    base = Path(root).expanduser().resolve()
    spec = read_json(base / "film-spec.json") or {}
    package = read_json(base / "dialogue-scene-package.json") or {}
    try:
        validate_film_spec(spec, assign_missing_ids=False)
    except FilmSpecError as exc:
        raise ValueError("DIALOGUE_PRODUCTION_PLAN_FILM_SPEC_INVALID") from exc
    validation = validate_dialogue_scene_package(package)
    if spec.get("vo_mode") != "dialogue_drama":
        raise ValueError("DIALOGUE_PRODUCTION_PLAN_REQUIRES_DIALOGUE_DRAMA")
    if not validation.get("ok"):
        raise ValueError("DIALOGUE_PRODUCTION_PLAN_PACKAGE_INVALID")

    by_line = _shots(spec)
    stages: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for scene in package.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for line in scene.get("lines") or []:
            if not isinstance(line, dict):
                continue
            line_id = str(line["line_id"])
            mode = str(line["screen_mode"])
            shot = by_line.get(line_id, {})
            state_id = str(line["scene_state_id"])
            audio = line.get("audio") if isinstance(line.get("audio"), dict) else {}
            tts = _stage(
                f"{line_id}:tts",
                line_id=line_id,
                kind="locked_dialogue_tts",
                tool="character_voice_lock_and_audio_timeline",
                depends_on=[],
                evidence_required=["audio_path", "audio_sha256", "measured_duration_sec", "pauses"],
            )
            stages.append(tts)
            state = _stage(
                f"{line_id}:state-photo",
                line_id=line_id,
                kind="performance_state_photo",
                tool="comfy_qwen_i2i_performance_state",
                depends_on=[tts["stage_id"]],
                evidence_required=[
                    "approved_state_photo",
                    "input_sha256",
                    "output_sha256",
                    "model",
                ],
            )
            stages.append(state)
            keyframe = _stage(
                f"{line_id}:keyframe",
                line_id=line_id,
                kind="performance_keyframe",
                tool="comfy_qwen_i2i_keyframe",
                depends_on=[state["stage_id"]],
                evidence_required=[
                    "keyframe_path",
                    "state_photo_sha256",
                    "output_sha256",
                    "composition_review",
                ],
            )
            stages.append(keyframe)
            frw_upload = _stage(
                f"{line_id}:frw-keyframe-upload",
                line_id=line_id,
                kind="frw_i2v_keyframe_upload",
                tool="frw_upload_image",
                depends_on=[keyframe["stage_id"]],
                evidence_required=[
                    "approved_keyframe_path",
                    "keyframe_sha256",
                    "uploaded_img_url",
                    "upload_receipt",
                ],
            )
            stages.append(frw_upload)
            i2v = _stage(
                f"{line_id}:i2v",
                line_id=line_id,
                kind="native_audio_dialogue_i2v",
                tool="frw_ltx23_img2video_audio",
                depends_on=[frw_upload["stage_id"]],
                evidence_required=[
                    "frw_task_id",
                    "native_mp4",
                    "ffprobe",
                    "motion_review",
                    "native_audio_dialogue_review",
                    "provider_prompt_no_visible_text",
                ],
            )
            stages.append(i2v)
            # Every provider I2V clip is scanned: visual text can appear in B-roll
            # and non-lipsync shots just as readily as in dialogue close-ups.
            requires_visual_text_audit = True
            if requires_visual_text_audit:
                visual_text_audit = _stage(
                    f"{line_id}:visual-text-audit",
                    line_id=line_id,
                    kind="provider_visual_text_audit",
                    tool="visual-text-audit",
                    depends_on=[i2v["stage_id"]],
                    evidence_required=[
                        "clip_sha256",
                        "every_decoded_frame_scan",
                        "visual_text_audit_receipt",
                    ],
                )
                stages.append(visual_text_audit)
                visual_text_repair = _stage(
                    f"{line_id}:visual-text-repair",
                    line_id=line_id,
                    kind="provider_visual_text_repair",
                    tool="visual-text-repair",
                    depends_on=[visual_text_audit["stage_id"]],
                    activation="only_after_provider_visual_text_rejected",
                    evidence_required=[
                        "repair_receipt",
                        "repaired_clip_sha256",
                        "clean_reaudit_receipt",
                    ],
                )
                stages.append(visual_text_repair)
                native_text_gate = _stage(
                    f"{line_id}:native-text-gate",
                    line_id=line_id,
                    kind="native_text_rejection_gate",
                    tool="native_text_gate.validate_native_text_review",
                    depends_on=[visual_text_audit["stage_id"], visual_text_repair["stage_id"]],
                    evidence_required=[
                        "clip_sha256",
                        "sampled_frames",
                        "unexpected_visual_text_detected_false",
                        "matching_clean_visual_text_audit",
                        "native_audio_dialogue_matches_expected",
                        "mouth_audio_sync_approved",
                        "expected_duration_sec",
                        "native_duration_sec",
                        "caption_owner_ffmpeg_or_hyperframes_once",
                    ],
                )
                stages.append(native_text_gate)
                frw_i2v_fallback = _stage(
                    f"{line_id}:frw-i2v-fallback",
                    line_id=line_id,
                    kind="frw_i2v_visual_fallback",
                    tool="frw_img2video",
                    # The gate's recorded rejection is the authorization for a
                    # fallback. It is intentionally not an automatic retry.
                    depends_on=[frw_upload["stage_id"], native_text_gate["stage_id"]],
                    activation=(
                        "only_after_ltx_native_audio_rejection: "
                        "dialogue_mismatch|mouth_sync_failure|provider_visual_text|decode_failure"
                    ),
                    evidence_required=[
                        "frw_task_id",
                        "fallback_mp4",
                        "ffprobe",
                        "motion_review",
                        "provider_prompt_no_visible_text",
                        "fallback_reason",
                        "ltx_rejection_review",
                    ],
                )
                stages.append(frw_i2v_fallback)
                stages.append(
                    _stage(
                        f"{line_id}:latentsync-fallback",
                        line_id=line_id,
                        kind="visible_dialogue_lipsync_fallback",
                        tool="rtx_latentsync_1_6",
                        # The native-text gate is a branch: a rejected gate must not
                        # block the expensive fallback from receiving its rejection receipt.
                        depends_on=[frw_i2v_fallback["stage_id"], tts["stage_id"]],
                        activation=(
                            "only_after_ltx_native_audio_rejection: "
                            "dialogue_mismatch|mouth_sync_failure|provider_visual_text|decode_failure"
                        ),
                        evidence_required=[
                            "lipsync_mp4",
                            "tts_sha256",
                            "human_face_review",
                            "fallback_reason",
                            "ltx_rejection_review",
                        ],
                    )
                )
            stages.append(
                _stage(
                    f"{line_id}:sound",
                    line_id=line_id,
                    kind="foley_ambience",
                    tool="mmaudio_or_audio_node_with_foley_plan",
                    depends_on=[i2v["stage_id"]],
                    evidence_required=["foley_cues", "ambience_cues", "mix_track"],
                )
            )
            coverage.append(
                {
                    "line_id": line_id,
                    "screen_mode": mode,
                    "shot_id": str(shot.get("id") or line.get("shot_id") or ""),
                    "scene_state_id": state_id,
                    "audio_locked": audio.get("status") == "measured",
                    "requires_lipsync": mode == "on_camera" and bool(line.get("lipsync_required")),
                    "primary_dialogue_route": (
                        "frw_ltx23_img2video_audio"
                        if mode == "on_camera" and bool(line.get("lipsync_required"))
                        else None
                    ),
                    "fallback_dialogue_route": (
                        "frw_img2video_rejection_only"
                        if mode == "on_camera" and bool(line.get("lipsync_required"))
                        else None
                    ),
                }
            )

    plan = {
        "schema_version": 1,
        "kind": "dialogue-production-plan",
        "created_at": utc_now(),
        "root": str(base),
        "mode": "dialogue_drama",
        "route": {
            "state_photo": "comfy_qwen_i2i_performance_state",
            "keyframe": "comfy_qwen_i2i_keyframe",
            "dialogue_i2v_primary": "frw_ltx23_img2video_audio",
            "dialogue_i2v_fallback": "frw_img2video_rejection_only",
            "native_text_gate": "reject_provider_burned_text_before_post",
            "lipsync_primary": "frw_ltx23_native_audio_i2v_human_verified",
            "lipsync_fallback": "rtx_latentsync_1_6_after_frw_img2video_fallback",
            "sound": "mmaudio_or_audio_node_with_foley_plan",
            "post": "post-plan.json_to_final_to_review",
        },
        "coverage": coverage,
        "stages": stages,
        "post": {
            "depends_on": [
                stage["stage_id"] for stage in stages if stage["kind"] == "foley_ambience"
            ],
            "tool": "post-plan.json_to_final_to_review",
            "evidence_required": [
                "media_decode",
                "subtitle_audit",
                "caption_owner_ffmpeg_or_hyperframes_once",
                "dialogue_route_acceptance",
                "mix_audit",
                "human_final_review",
            ],
        },
    }
    write_json(base / _PLAN_NAME, plan)
    return plan
