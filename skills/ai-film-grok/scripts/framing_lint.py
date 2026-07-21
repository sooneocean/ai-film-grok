#!/usr/bin/env python3
"""Framing iron rules sedimented from ai-film-cn.

Crop-prone / head-crop language is linted on write-spec so still + I2V prompts
keep full head + headroom + subject framed (P0 readable + P4 semantic binding).
"""

from __future__ import annotations

import re
from typing import Any

# Phrases that historically caused head crops / subject pushed out of frame (cn 2026-07-14).
CROP_PRONE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"extreme\s*close[- ]?up", re.I),
    re.compile(r"\becu\b", re.I),
    re.compile(r"tight\s*close[- ]?up", re.I),
    re.compile(r"fill(?:s|ing)?\s+(?:the\s+)?frame", re.I),
    re.compile(r"face\s+fills?", re.I),
    re.compile(r"crop(?:ped|ping)?\s+(?:head|chin|forehead|face|top)", re.I),
    re.compile(r"(?:cut|chop)(?:s|ped|ping)?\s+off\s+(?:head|chin|forehead|hair)", re.I),
    re.compile(r"no\s+headroom", re.I),
    re.compile(r"push[- ]?in\s+on\s+(?:the\s+)?(?:face|eyes)", re.I),
    re.compile(r"low[- ]angle\s+face", re.I),
    re.compile(r"cropped?\s+(?:at\s+)?(?:the\s+)?(?:forehead|hairline)", re.I),
    re.compile(r"top\s+of\s+(?:the\s+)?head\s+(?:cut|crop|off)", re.I),
)

# Positive framing discipline (cn medium + headroom hard words).
SAFE_FRAMING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"full\s+head", re.I),
    re.compile(r"headroom", re.I),
    re.compile(r"head\s+and\s+(?:both\s+)?shoulders", re.I),
    re.compile(r"safe\s+framing", re.I),
    re.compile(r"no\s+crop(?:ping)?", re.I),
    re.compile(r"subject\s+stays\s+(?:framed|centered|visible)", re.I),
    re.compile(r"waist[- ]?up", re.I),
    re.compile(r"limbs\s+not\s+cropped", re.I),
)

SAFE_FRAMING_HINT = (
    "full head and both shoulders inside frame, ample headroom, "
    "safe framing no cropping, subject stays framed"
)

# Beats where subject head/body readability is critical (not pure detail insert).
SUBJECT_BEATS = frozenset({"hook", "approach", "action", "reaction", "afterglow", "bridge"})


def _shot_framing_blob(shot: dict[str, Any]) -> str:
    parts: list[str] = []
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    camera = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    for key in ("framing", "composition", "shot_size"):
        val = dsl.get(key) or camera.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
    motion = dsl.get("motion")
    if isinstance(motion, str) and motion.strip():
        parts.append(motion.strip())
    action = dsl.get("action")
    if isinstance(action, str) and action.strip():
        parts.append(action.strip())
    # top-level optional fields
    for key in ("framing", "still_prompt", "i2v_prompt"):
        val = shot.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
    return " | ".join(parts)


def _match_any(text: str, patterns: tuple[re.Pattern[str], ...]) -> list[str]:
    hits: list[str] = []
    for pat in patterns:
        m = pat.search(text or "")
        if m:
            hits.append(m.group(0))
    return hits


def lint_framing_iron(shots: list[dict[str, Any]]) -> dict[str, Any]:
    """Lint crop-prone framing language across shots.

    Returns:
      ok: True when no crop-risk issues
      codes: unique issue codes
      warning_count / error_count
      issues: list of {shot_id, code, message, level, hits?}
    """
    issues: list[dict[str, Any]] = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("id") or "?")
        blob = _shot_framing_blob(shot)
        if not blob.strip():
            continue
        crop_hits = _match_any(blob, CROP_PRONE_PATTERNS)
        if crop_hits:
            issues.append(
                {
                    "shot_id": sid,
                    "code": "FRAMING_CROP_RISK",
                    "level": "warning",
                    "message": (
                        f"{sid}: crop-prone framing language {crop_hits!r} — "
                        f"prefer medium/waist-up with headroom; hint: {SAFE_FRAMING_HINT}"
                    ),
                    "hits": crop_hits,
                }
            )
        beat = str(shot.get("dramatic_function") or "").strip().lower()
        if beat in SUBJECT_BEATS:
            safe_hits = _match_any(blob, SAFE_FRAMING_PATTERNS)
            # Only flag when framing-ish text exists but lacks safety tokens
            has_framing_field = False
            dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
            camera = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
            for val in (dsl.get("framing"), camera.get("framing"), shot.get("framing")):
                if isinstance(val, str) and val.strip():
                    has_framing_field = True
                    break
            if has_framing_field and not safe_hits and not crop_hits:
                # soft nudge only when no crop risk already reported
                issues.append(
                    {
                        "shot_id": sid,
                        "code": "FRAMING_HEADROOM_MISS",
                        "level": "warning",
                        "message": (
                            f"{sid}: framing lacks full-head/headroom/safe-framing tokens — "
                            f"add: {SAFE_FRAMING_HINT}"
                        ),
                        "hits": [],
                    }
                )

    codes = sorted({str(i["code"]) for i in issues})
    warning_count = sum(1 for i in issues if i.get("level") == "warning")
    error_count = sum(1 for i in issues if i.get("level") == "error")
    return {
        "ok": warning_count == 0 and error_count == 0,
        "codes": codes,
        "warning_count": warning_count,
        "error_count": error_count,
        "issues": issues,
        "note": (
            "Soft: ban crop-prone ECU/fill-frame/push-in-on-face language; "
            "keep full head + headroom + subject stays framed "
            "(sediment from ai-film-cn). Strict: framing_strict: true"
        ),
    }


def framing_crop_risk_in_text(text: str) -> list[str]:
    """Public helper for unit tests / still-prompt gates."""
    return _match_any(text or "", CROP_PRONE_PATTERNS)
