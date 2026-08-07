"""Cinematography rules table — emotion/purpose → lens language (Film Production OS W7).

Data-driven suggestions only. Does not rewrite film-spec; adapters may read lookup.
"""

from __future__ import annotations

from typing import Any

# emotion / purpose key → framing + camera language
CINE_RULES: dict[str, dict[str, str]] = {
    "tension": {
        "shot_size": "mcu",
        "angle": "eye_level",
        "lens": "50mm_equiv",
        "camera_motion": "slow_push_or_hold",
        "note": "tighten space; hold beats before cut",
    },
    "fear": {
        "shot_size": "cu",
        "angle": "slight_low",
        "lens": "35mm_equiv",
        "camera_motion": "handheld_micro",
        "note": "unstable micro-move; avoid wide comfort",
    },
    "intimacy": {
        "shot_size": "ecu_or_cu",
        "angle": "eye_level",
        "lens": "85mm_equiv",
        "camera_motion": "breathing_hold",
        "note": "shallow space; prioritize eyes/skin texture",
    },
    "reveal": {
        "shot_size": "ms_to_ws",
        "angle": "eye_level",
        "lens": "35mm_equiv",
        "camera_motion": "pull_back_or_pan",
        "note": "information entrance; land on readable geography",
    },
    "action": {
        "shot_size": "ms",
        "angle": "dynamic",
        "lens": "35mm_equiv",
        "camera_motion": "follow_or_whip",
        "note": "body readable; cut on action peaks",
    },
    "afterglow": {
        "shot_size": "ms_or_cu",
        "angle": "soft_high",
        "lens": "50mm_equiv",
        "camera_motion": "static_or_drift",
        "note": "release energy; longer holds ok",
    },
    "dialogue": {
        "shot_size": "mcu",
        "angle": "eyeline",
        "lens": "50mm_equiv",
        "camera_motion": "locked_or_slow_dolly",
        "note": "protect eyeline; reverse coverage",
    },
    "establish": {
        "shot_size": "ws",
        "angle": "eye_or_high",
        "lens": "24mm_equiv",
        "camera_motion": "static_or_slow_pan",
        "note": "geography first; one clear read",
    },
}

_PURPOSE_TO_KEY: dict[str, str] = {
    "create_tension": "tension",
    "show_reaction": "tension",
    "emotional_closeup": "intimacy",
    "reveal_information": "reveal",
    "story_reveal": "reveal",
    "action_coverage": "action",
    "release_tension": "afterglow",
    "dialogue_coverage": "dialogue",
    "establish_location": "establish",
    "establish_geography": "establish",
    "insert_detail": "intimacy",
    "subjective_pov": "fear",
}


def _norm(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def lookup_cine_rule(
    *,
    emotion: str = "",
    purpose: str = "",
    dramatic_function: str = "",
) -> dict[str, Any]:
    """Return best-match rule + resolved key (or empty suggestion)."""
    emo = _norm(emotion)
    purpose_n = _norm(purpose)
    fn = _norm(dramatic_function)

    key = ""
    if emo in CINE_RULES:
        key = emo
    elif purpose_n in _PURPOSE_TO_KEY:
        key = _PURPOSE_TO_KEY[purpose_n]
    elif purpose_n in CINE_RULES:
        key = purpose_n
    elif fn in {"hook", "approach"}:
        key = "establish" if fn == "hook" else "tension"
    elif fn in {"action", "sensory", "reaction", "afterglow", "bridge"}:
        key = {
            "action": "action",
            "sensory": "intimacy",
            "reaction": "tension",
            "afterglow": "afterglow",
            "bridge": "establish",
        }[fn]

    if not key or key not in CINE_RULES:
        return {
            "ok": True,
            "matched": False,
            "key": None,
            "rule": None,
        }
    rule = dict(CINE_RULES[key])
    return {
        "ok": True,
        "matched": True,
        "key": key,
        "rule": rule,
        "shot_size": rule.get("shot_size"),
        "angle": rule.get("angle"),
        "lens": rule.get("lens"),
        "camera_motion": rule.get("camera_motion"),
        "note": rule.get("note"),
    }


def enrich_shot_spec_with_cine(shot_spec: dict[str, Any]) -> dict[str, Any]:
    """Non-mutating: return new dict with cine_suggestion when framing empty."""
    out = dict(shot_spec)
    framing = out.get("framing") if isinstance(out.get("framing"), dict) else {}
    perf = out.get("performance") if isinstance(out.get("performance"), dict) else {}
    look = lookup_cine_rule(
        emotion=str(perf.get("emotion") or ""),
        purpose=str(out.get("shot_purpose") or ""),
        dramatic_function=str(out.get("dramatic_function") or ""),
    )
    out["cine_suggestion"] = look
    if look.get("matched") and isinstance(framing, dict):
        filled = dict(framing)
        if not filled.get("shot_size") and look.get("shot_size"):
            filled["shot_size"] = look["shot_size"]
        if not filled.get("angle") and look.get("angle"):
            filled["angle"] = look["angle"]
        if not filled.get("lens") and look.get("lens"):
            filled["lens"] = look["lens"]
        out["framing"] = filled
    return out
