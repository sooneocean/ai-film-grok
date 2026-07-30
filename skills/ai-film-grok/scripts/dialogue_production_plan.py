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
) -> dict[str, Any]:
    return {
        "stage_id": stage_id,
        "line_id": line_id,
        "kind": kind,
        "tool": tool,
        "depends_on": depends_on,
        "execution": "manual_verified_only",
        "evidence_required": evidence_required,
    }


def build_dialogue_production_plan(root: Path | str) -> dict[str, Any]:
    """Return the explicit line-keyed Qwen → Wan → LatentSync/post workflow.

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
            i2v = _stage(
                f"{line_id}:i2v",
                line_id=line_id,
                kind="performance_i2v",
                tool="comfy_wan22_i2v",
                depends_on=[keyframe["stage_id"]],
                evidence_required=["mp4_path", "ffprobe", "motion_review", "last_frame_candidate"],
            )
            stages.append(i2v)
            if mode == "on_camera" and bool(line.get("lipsync_required")):
                stages.append(
                    _stage(
                        f"{line_id}:lipsync",
                        line_id=line_id,
                        kind="visible_dialogue_lipsync",
                        tool="rtx_latentsync_1_6",
                        depends_on=[i2v["stage_id"], tts["stage_id"]],
                        evidence_required=["lipsync_mp4", "tts_sha256", "human_face_review"],
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
            "i2v": "comfy_wan22_i2v",
            "lipsync_primary": "rtx_latentsync_1_6",
            "lipsync_fallback": "rtx_musetalk_1_5_classified_technical_failure_only",
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
                "mix_audit",
                "human_final_review",
            ],
        },
    }
    write_json(base / _PLAN_NAME, plan)
    return plan
