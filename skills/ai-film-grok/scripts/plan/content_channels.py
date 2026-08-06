#!/usr/bin/env python3
"""Separate authored words from visible performance and generated motion."""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDERS = frozenset({"", "none", "n/a", "needs_authoring", "待补写", "无"})
_VOICE_WORDS = ("旁白", "台词", "对白", "dialogue", "narration", "voiceover", "vo")


def _text(value: object) -> str:
    return str(value or "").strip()


def _present(value: object) -> bool:
    return _text(value).lower() not in _PLACEHOLDERS


def _dialogue_text(shot: dict[str, Any]) -> str:
    raw = shot.get("dialogue") or shot.get("dialogue_text") or shot.get("lines") or ""
    if isinstance(raw, list):
        return " ".join(
            _text(item.get("text") if isinstance(item, dict) else item) for item in raw
        ).strip()
    return _text(raw)


def resolve_content_channels(shot: dict[str, Any]) -> dict[str, Any]:
    """Return the explicit authoring contract with safe legacy inference.

    ``nar`` is always audio/editorial text.  It is deliberately never used as
    an action fallback.  A shot gets character motion only from visual action,
    performance fields, and a declared/inferred in-scene trigger.
    """
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    authored = (
        shot.get("content_channels") if isinstance(shot.get("content_channels"), dict) else {}
    )
    voice_in = authored.get("voice") if isinstance(authored.get("voice"), dict) else {}
    perf_in = authored.get("performance") if isinstance(authored.get("performance"), dict) else {}
    motion_in = authored.get("motion") if isinstance(authored.get("motion"), dict) else {}

    dialogue = (
        _text(voice_in.get("text")) if voice_in.get("kind") == "dialogue" else _dialogue_text(shot)
    )
    nar = _text(shot.get("nar"))
    voice_kind = _text(voice_in.get("kind")).lower()
    if voice_kind not in {"narration", "dialogue", "none"}:
        voice_kind = "dialogue" if dialogue else ("narration" if nar else "none")
    voice_text = _text(voice_in.get("text")) or (dialogue if voice_kind == "dialogue" else nar)
    lipsync = shot.get("lipsync") is True or _text(shot.get("lipsync")).lower() in {
        "on",
        "required",
        "true",
    }
    on_camera = bool(voice_in.get("on_camera", shot.get("speaker_on_camera", lipsync)))

    visual_action = _text(motion_in.get("action")) or _text(dsl.get("action"))
    playable_action = _text(perf_in.get("playable_action")) or _text(shot.get("playable_action"))
    reaction_trigger = _text(perf_in.get("reaction_trigger")) or _text(shot.get("reaction_trigger"))
    body_state = _text(perf_in.get("body_state")) or _text(shot.get("body_state"))
    gaze_target = _text(perf_in.get("gaze_target")) or _text(shot.get("gaze_target"))
    scene_trigger = (
        _text(motion_in.get("scene_trigger"))
        or _text(perf_in.get("scene_trigger"))
        or _text(shot.get("scene_trigger"))
    )
    if not _present(scene_trigger):
        if _present(reaction_trigger):
            scene_trigger = reaction_trigger
        elif _present(visual_action) or _present(playable_action):
            scene_trigger = "action_start"
        else:
            scene_trigger = "none"

    return {
        "voice": {
            "kind": voice_kind,
            "text": voice_text,
            "on_camera": on_camera,
            "lipsync": lipsync,
        },
        "performance": {
            "playable_action": playable_action,
            "reaction_trigger": reaction_trigger,
            "body_state": body_state,
            "gaze_target": gaze_target,
        },
        "motion": {
            "action": visual_action,
            "camera_motion": _text(motion_in.get("camera_motion")) or _text(dsl.get("motion")),
            "scene_trigger": scene_trigger,
        },
    }


def visual_prompt_action(shot: dict[str, Any]) -> str:
    """Build a visual-only action clause; intentionally excludes spoken text."""
    channels = resolve_content_channels(shot)
    perf = channels["performance"]
    pieces = [channels["motion"]["action"], perf["playable_action"]]
    if _present(perf["reaction_trigger"]) and (
        _present(perf["body_state"]) or _present(perf["gaze_target"])
    ):
        response = ", ".join(x for x in (perf["body_state"], perf["gaze_target"]) if _present(x))
        pieces.append(f"after {perf['reaction_trigger']}: {response}")
    seen: set[str] = set()
    clean: list[str] = []
    for item in pieces:
        key = _text(item).lower()
        if _present(key) and key not in seen:
            seen.add(key)
            clean.append(_text(item))
    return "; ".join(clean)


def lint_content_channels(shots: list[dict[str, Any]]) -> dict[str, Any]:
    """Lint the boundary: words are not automatic performance or movement."""
    issues: list[dict[str, Any]] = []
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            continue
        sid = _text(shot.get("id")) or f"shot{index + 1}"
        channels = resolve_content_channels(shot)
        voice, perf, motion = channels["voice"], channels["performance"], channels["motion"]
        nar = _text(shot.get("nar"))
        action = _text(motion["action"])
        explicit = isinstance(shot.get("content_channels"), dict)

        if action and nar and re.sub(r"\s+", "", action) == re.sub(r"\s+", "", nar):
            issues.append(
                {
                    "code": "TEXT_USED_AS_VISUAL_ACTION",
                    "severity": "error",
                    "shot_id": sid,
                    "message": f"{sid}: nar 是音频文本，不能原样充当 dsl.action；补写可观察动作。",
                }
            )
        if voice["kind"] == "dialogue" and voice["on_camera"] and not voice["lipsync"]:
            issues.append(
                {
                    "code": "ON_CAMERA_DIALOGUE_LIPSYNC_OFF",
                    "severity": "error",
                    "shot_id": sid,
                    "message": f"{sid}: 镜内台词要求嘴型，但 lipsync 未开启；改为画外台词或明确启用 lipsync。",
                }
            )
        if voice["lipsync"] and voice["kind"] != "dialogue":
            issues.append(
                {
                    "code": "LIPSYNC_WITHOUT_DIALOGUE",
                    "severity": "error",
                    "shot_id": sid,
                    "message": f"{sid}: lipsync 只能由 dialogue 触发，不能由旁白触发。",
                }
            )
        if _present(perf["reaction_trigger"]) and any(
            word in perf["reaction_trigger"].lower() for word in _VOICE_WORDS
        ):
            issues.append(
                {
                    "code": "TEXT_ONLY_REACTION_TRIGGER",
                    "severity": "error",
                    "shot_id": sid,
                    "message": f"{sid}: 反应触发器必须是场内事件（物件/动作/信息显现），不能只写旁白或台词。",
                }
            )
        actor_motion = (
            _present(action)
            or _present(perf["playable_action"])
            or _present(perf["reaction_trigger"])
        )
        authored_motion = shot.get("content_channels") if explicit else {}
        authored_perf = (
            authored_motion.get("performance")
            if isinstance(authored_motion.get("performance"), dict)
            else {}
        )
        authored_move = (
            authored_motion.get("motion") if isinstance(authored_motion.get("motion"), dict) else {}
        )
        authored_trigger = (
            _text(authored_move.get("scene_trigger"))
            or _text(authored_perf.get("scene_trigger"))
            or _text(shot.get("scene_trigger"))
        )
        if explicit and actor_motion and not _present(authored_trigger):
            issues.append(
                {
                    "code": "PERFORMANCE_TRIGGER_MISSING",
                    "severity": "error",
                    "shot_id": sid,
                    "message": f"{sid}: 表演/动态缺少 scene_trigger；说明哪一个场内事件启动动作。",
                }
            )
        if (
            voice["kind"] == "narration"
            and not voice["lipsync"]
            and not action
            and not _present(perf["playable_action"])
        ):
            # This is valid: establish/insert may be audio plus camera only.
            continue

    errors = [issue for issue in issues if issue["severity"] == "error"]
    return {
        "ok": not errors,
        "codes": sorted({str(issue["code"]) for issue in issues}),
        "issues": issues,
        "error_count": len(errors),
        "warning_count": 0,
        "note": "nar/dialogue are audio; performance and motion require scene triggers.",
    }
