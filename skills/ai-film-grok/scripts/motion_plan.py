#!/usr/bin/env python3
"""Deterministic panel-animation motion plans for non-I2V shots."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from content_channels import resolve_content_channels
from util import read_json, utc_now, write_json


class MotionPlanError(ValueError):
    pass


def build_motion_plan(root: Path, shot_id: str) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json") or {}
    found: dict[str, Any] | None = None
    for scene in spec.get("scenes") or []:
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict) and str(shot.get("id")) == shot_id:
                found = shot
                break
    if found is None:
        raise MotionPlanError(f"shot not found in film-spec: {shot_id}")
    dsl = found.get("dsl") if isinstance(found.get("dsl"), dict) else {}
    channels = resolve_content_channels(found)
    motion = str(dsl.get("motion") or "hold").strip().lower().replace(" ", "_")
    allowed = {"hold", "push_in", "pull_back", "pan", "parallax", "ken_burns", "locked"}
    if motion not in allowed:
        motion = "hold"
    duration = float(found.get("duration_sec") or 5.0)
    plan = {
        "schema_version": 1,
        "kind": "panel-animation-motion-plan",
        "ok": True,
        "shot_id": shot_id,
        "production_mode": "panel-animation",
        "operation": motion,
        "scene_trigger": channels["motion"]["scene_trigger"],
        "character_action": channels["motion"]["action"],
        "playable_action": channels["performance"]["playable_action"],
        "voice_kind": channels["voice"]["kind"],
        "lipsync": channels["voice"]["lipsync"],
        "duration_sec": duration,
        "start_scale": 1.0,
        "end_scale": 1.06 if motion in {"push_in", "ken_burns"} else 1.0,
        "start_offset": [0.0, 0.0],
        "end_offset": [0.02, 0.0] if motion == "pan" else [0.0, 0.0],
        "source_keyframe": str(root / "keyframes" / f"{shot_id}.png"),
        "human_motion_claim": False,
        "created_at": utc_now(),
        "note": "Panel animation is deterministic post motion; it does not prove character performance or convert narration into acting.",
    }
    out = root / "receipts" / "motion-plans" / f"{shot_id}.json"
    write_json(out, plan)
    plan["path"] = str(out)
    return plan
