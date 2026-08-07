"""Emotion → camera language mapping (Film Production OS W7).

Data-driven cinematography rules — not random cinematic vocabulary.
Story intent maps to framing / lens / motion / focus.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

# Canonical story-emotion / intent keys → camera prescription
CINE_RULES: dict[str, dict[str, str]] = {
    "emotional_isolation": {
        "focal_length": "longer",
        "space": "compressed",
        "background": "limited_context",
        "motion": "static_or_slow",
        "why": "isolate subject from world",
    },
    "loss_of_control": {
        "focal_length": "normal_to_wide",
        "space": "unstable",
        "background": "open",
        "motion": "increasingly_unstable_handheld",
        "why": "destabilize audience with subject",
    },
    "discovery": {
        "focal_length": "normal",
        "space": "opening",
        "background": "reveal_context",
        "motion": "controlled_push_in",
        "why": "draw attention to new information",
    },
    "power_imbalance": {
        "focal_length": "normal",
        "space": "vertical_hierarchy",
        "background": "support_elevation",
        "motion": "static_hold",
        "angle": "elevation_difference",
        "why": "who holds power is visible in height",
    },
    "subjective_confusion": {
        "focal_length": "shallow_selective",
        "space": "obstructed",
        "background": "defocused",
        "motion": "drift_or_obstruction",
        "focus": "selective_focus",
        "why": "limit knowledge to character POV",
    },
    "tension": {
        "focal_length": "medium_long",
        "space": "tightening",
        "background": "threat_in_frame_edge",
        "motion": "slow_creep",
        "why": "withhold release",
    },
    "intimacy": {
        "focal_length": "85mm_class",
        "space": "close",
        "background": "soft",
        "motion": "gentle_orbit_or_static",
        "why": "emotional proximity",
    },
    "action": {
        "focal_length": "wide_to_normal",
        "space": "readable_geography",
        "background": "clear_axes",
        "motion": "motivated_follow",
        "why": "event first, camera serves event",
    },
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _norm(value: object) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def map_intent_to_camera(intent: str) -> dict[str, Any] | None:
    key = _norm(intent)
    # aliases
    aliases = {
        "isolation": "emotional_isolation",
        "alone": "emotional_isolation",
        "chaos": "loss_of_control",
        "panic": "loss_of_control",
        "reveal": "discovery",
        "power": "power_imbalance",
        "confusion": "subjective_confusion",
        "pov": "subjective_confusion",
        "suspense": "tension",
        "close": "intimacy",
        "sex": "intimacy",
        "fight": "action",
        "motion": "action",
    }
    key = aliases.get(key, key)
    rule = CINE_RULES.get(key)
    if not rule:
        return None
    return {"intent": key, "camera": dict(rule)}


def resolve_shot_cinematography(shot: dict[str, Any]) -> dict[str, Any]:
    """Resolve camera language for a shot from explicit intent or dramatic purpose."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    explicit = _text(
        shot.get("cinematography_intent")
        or shot.get("visual_strategy")
        or dsl.get("cinematography_intent")
    )
    mapped = map_intent_to_camera(explicit) if explicit else None
    if not mapped:
        purpose = _norm(shot.get("shot_purpose") or shot.get("dramatic_function"))
        purpose_map = {
            "create_tension": "tension",
            "subjective_pov": "subjective_confusion",
            "emotional_closeup": "intimacy",
            "action_coverage": "action",
            "story_reveal": "discovery",
            "reveal_information": "discovery",
            "action": "action",
            "reaction": "intimacy",
            "hook": "discovery",
        }
        mapped = map_intent_to_camera(purpose_map.get(purpose, "")) if purpose_map.get(purpose) else None
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    authored = {
        "shot_size": _text(shot.get("shot_size") or dsl.get("shot_size")),
        "lens": _text(shot.get("lens") or dsl.get("lens")),
        "camera_motion": _text(shot.get("camera") or dsl.get("camera") or dsl.get("camera_motion")),
        "angle": _text(shot.get("angle") or dsl.get("angle")),
    }
    return {
        "shot_id": _text(shot.get("id")),
        "intent_map": mapped,
        "authored": authored,
        "instruction": _format_instruction(mapped, authored),
    }


def _format_instruction(mapped: dict[str, Any] | None, authored: dict[str, str]) -> str:
    parts: list[str] = []
    if mapped:
        cam = mapped.get("camera") or {}
        parts.append(f"Intent={mapped.get('intent')}")
        for k in ("focal_length", "motion", "space", "focus", "angle", "why"):
            if cam.get(k):
                parts.append(f"{k}={cam[k]}")
    for k, v in authored.items():
        if v:
            parts.append(f"{k}={v}")
    return "; ".join(parts) if parts else "Camera serves story event; avoid unmotivated moves."


def list_cine_rules() -> dict[str, Any]:
    return {
        "ok": True,
        "kind": "cinematography-rules",
        "intents": sorted(CINE_RULES.keys()),
        "rules": CINE_RULES,
    }


def cinematography_for_spec(spec: dict[str, Any]) -> dict[str, Any]:
    shots: list[dict[str, Any]] = []
    for sc in spec.get("scenes") or []:
        if not isinstance(sc, dict):
            continue
        for sh in sc.get("shots") or []:
            if isinstance(sh, dict):
                shots.append(sh)
    resolved = [resolve_shot_cinematography(s) for s in shots]
    return {
        "ok": True,
        "kind": "cinematography-resolve",
        "count": len(resolved),
        "shots": resolved,
    }


def cinematography_at_root(
    root: Path | str,
    *,
    write_receipt: bool = True,
) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    spec = read_json(root_p / "film-spec.json") or {}
    if not isinstance(spec, dict):
        return {"ok": False, "error": "film-spec missing"}
    report = cinematography_for_spec(spec)
    report["rules_available"] = sorted(CINE_RULES.keys())
    report["root"] = str(root_p)
    report["at"] = utc_now()
    if write_receipt:
        path = root_p / "receipts" / "cinematography.json"
        write_json(path, report)
        report["receipt"] = str(path)
    return report
