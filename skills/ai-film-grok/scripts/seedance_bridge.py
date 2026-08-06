#!/usr/bin/env python3
"""Seedance prompt bridge — convert cinema_prompt DSL into Seedance structured prompts.

Seedance (songguoxs/seedance-prompt-skill) expects structured Chinese prompts with:
  - subject + action line (prefixed with @Image1 for I2V)
  - camera language (move/angle/pacing)
  - visual style (lighting/palette/grain)
  - optional negative prompt
  - timestamp storyboarding for clips >15s (multi-segment stitching)

This module reads ``dsl.camera_prompt`` (produced by ``cinema_prompt``) plus the
shot's subject/action and composes a single Seedance-ready prompt string, so the
SeedanceProvider can pass it to ``--prompt`` directly.

Pure deterministic composition — no external LLM, no network.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, write_json


class SeedanceBridgeError(ValueError):
    pass


# Seedance negative-prompt vocabulary (defaults; overridable per scene_type)
DEFAULT_NEGATIVES = {
    "short_drama": "模糊, 变形, 多余手指, 低画质, 水印, 字幕, 静帧无运动",
    "ecchi_romance": "崩坏, 多余肢体, 穿脱矛盾, 回穿, 静帧, 口型不同步, 低画质",
    "ecommerce": "模糊, 低质感, 水印, 镜头抖动, 曝光过度",
    "xianxia": "现代物件, 穿帮, 低画质, 变形, 多余手指",
    "science": "模糊, 数据错误, 低画质, 水印, 镜头抖动",
    "music_video": "静帧, 节奏脱拍, 模糊, 低画质, 变形",
}


def build_seedance_prompt(
    *,
    subject: str = "",
    action: str = "",
    camera_prompt: str = "",
    scene_type: str | None = None,
    duration_sec: float = 5.0,
    negative: str | None = None,
    image_marker: str = "@Image1",
) -> dict[str, Any]:
    """Compose a Seedance-structured Chinese prompt from cinema_prompt DSL.

    Returns ``{"prompt": str, "negative": str, "segments": list}`` where
    ``segments`` is non-empty only for clips >15s (Seedance multi-segment stitching).
    """
    if not camera_prompt and not subject and not action:
        raise SeedanceBridgeError("need at least one of camera_prompt/subject/action")

    parts: list[str] = []
    # Subject line with image marker for I2V
    if subject:
        parts.append(f"{image_marker} {subject}".strip())
    if action:
        parts.append(f"动作：{action}")
    if camera_prompt:
        parts.append(f"运镜/视觉：{camera_prompt}")

    prompt = "。".join(p for p in parts if p) + "。"

    # Negative prompt
    if negative is None:
        negative = DEFAULT_NEGATIVES.get(scene_type or "", DEFAULT_NEGATIVES["short_drama"])

    # Multi-segment storyboarding for >15s (Seedance's stitching strategy)
    segments: list[dict[str, Any]] = []
    if duration_sec > 15.0:
        n_seg = max(2, int(duration_sec // 10))
        seg_dur = round(duration_sec / n_seg, 1)
        for i in range(n_seg):
            t0 = round(i * seg_dur, 1)
            t1 = round(min((i + 1) * seg_dur, duration_sec), 1)
            segments.append(
                {
                    "index": i + 1,
                    "time": f"{t0:.1f}-{t1:.1f}s",
                    "prompt": prompt,  # Seedance re-applies; caller may vary per segment
                }
            )

    return {
        "prompt": prompt,
        "negative": negative,
        "segments": segments,
        "duration_sec": duration_sec,
        "scene_type": scene_type,
        "image_marker": image_marker,
    }


def bridge_shot(shot: dict[str, Any], *, scene_type: str | None = None) -> dict[str, Any]:
    """Bridge one film-spec shot's DSL into a Seedance prompt."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    camera_prompt = str(dsl.get("camera_prompt") or "").strip()
    subject = str(dsl.get("subject") or "").strip()
    action = str(dsl.get("action") or dsl.get("must_show") or "").strip()
    duration = float(shot.get("duration_sec") or 5.0)
    return build_seedance_prompt(
        subject=subject,
        action=action,
        camera_prompt=camera_prompt,
        scene_type=scene_type,
        duration_sec=duration,
    )


def bridge_film_spec(root: str | Any) -> dict[str, Any]:
    """Walk film-spec.json and bridge every shot's camera_prompt → Seedance prompt.

    Writes a receipt at ``receipts/seedance-prompt-bridge.json``.
    """
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json")
    if not spec:
        raise SeedanceBridgeError(f"film-spec.json not found or invalid in {root}")

    scene_type = str(spec.get("genre") or spec.get("scene_type") or "").strip().lower() or None
    bridged: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            result = bridge_shot(shot, scene_type=scene_type)
            result["shot_id"] = shot.get("id")
            bridged.append(result)

    from datetime import UTC, datetime

    receipt = {
        "schema_version": 1,
        "kind": "seedance-prompt-bridge",
        "ok": True,
        "shots_bridged": len(bridged),
        "scene_type": scene_type,
        "shots": bridged,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    out = root / "receipts" / "seedance-prompt-bridge.json"
    write_json(out, receipt)
    receipt["path"] = str(out)
    return receipt
