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

# A head must be entirely visible and have space above the hair.  One condition
# cannot substitute for the other.
FULL_HEAD_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"full\s+head", re.I),
    re.compile(r"head\s+and\s+(?:both\s+)?shoulders", re.I),
    re.compile(r"full\s+heads?\s+(?:both|of\s+both)", re.I),
)
HEADROOM_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?:ample\s+)?headroom", re.I),
    re.compile(r"space\s+above\s+(?:the\s+)?(?:hair|head)", re.I),
)
SAFE_FRAMING_PATTERNS: tuple[re.Pattern[str], ...] = (
    *FULL_HEAD_PATTERNS,
    *HEADROOM_PATTERNS,
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

VERTICAL_SAFE_AREA_HINT = (
    "declare top_ui_clear, subtitle_clear, subject_clear and prop_readable "
    "for 9:16 platform framing"
)


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
                    "code": "HEAD_CROP",
                    "level": "error",
                    "message": (
                        f"{sid}: crop-prone framing language {crop_hits!r} — "
                        f"prefer medium/waist-up with headroom; hint: {SAFE_FRAMING_HINT}"
                    ),
                    "hits": crop_hits,
                }
            )
        beat = str(shot.get("dramatic_function") or "").strip().lower()
        if beat in SUBJECT_BEATS:
            full_head_hits = _match_any(blob, FULL_HEAD_PATTERNS)
            headroom_hits = _match_any(blob, HEADROOM_PATTERNS)
            # Only flag when framing-ish text exists but lacks the full lock.
            has_framing_field = False
            dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
            camera = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
            for val in (dsl.get("framing"), camera.get("framing"), shot.get("framing")):
                if isinstance(val, str) and val.strip():
                    has_framing_field = True
                    break
            if has_framing_field and (not full_head_hits or not headroom_hits) and not crop_hits:
                issues.append(
                    {
                        "shot_id": sid,
                        "code": "HEADROOM_MISS",
                        "level": "error",
                        "message": (
                            f"{sid}: framing must explicitly retain the full head and headroom — "
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
            "Hard: people-facing shots must explicitly retain a full head and "
            "headroom; crop-prone language is rejected."
        ),
    }


# P1-7: Composition + axis + eyeline + 30-degree + size progression lints

CODE_AXIS_BREAK = "AXIS_BREAK"
CODE_EYELINE_MISMATCH = "EYELINE_MISMATCH"
CODE_THIRTY_DEGREE_VIOLATION = "THIRTY_DEGREE_VIOLATION"
CODE_SIZE_PROGRESSION_FLAT = "SIZE_PROGRESSION_FLAT"

_SHOT_SIZE_ORDER = {
    "ews": 0,
    "extreme_wide": 0,
    "ws": 1,
    "wide": 1,
    "long": 1,
    "mws": 2,
    "medium_wide": 2,
    "ms": 3,
    "medium": 3,
    "mcu": 4,
    "medium_close_up": 4,
    "cu": 5,
    "close_up": 5,
    "ecu": 6,
    "extreme_close_up": 6,
}


def _axis_side(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return (
        str(
            shot.get("axis_side")
            or dsl.get("look_axis")
            or dsl.get("look_direction")
            or shot.get("look_axis")
            or ""
        )
        .strip()
        .lower()
    )


def _eyeline_target(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return (
        str(shot.get("eyeline_target") or dsl.get("gaze_target") or shot.get("gaze_target") or "")
        .strip()
        .lower()
    )


def _size_rank(shot: dict[str, Any]) -> int | None:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    cam = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    size = (
        str(shot.get("shot_size") or cam.get("shot_size") or dsl.get("shot_size") or "")
        .strip()
        .lower()
    )
    return _SHOT_SIZE_ORDER.get(size)


def lint_composition_rules(shots: list[dict[str, Any]]) -> dict[str, Any]:
    """P1-7: Lint 180° axis continuity, eyeline match, 30-degree rule, size progression.

    Returns {ok, issues, codes, warning_count, error_count}.
    """
    issues: list[dict[str, Any]] = []
    if len(shots) < 2:
        return {"ok": True, "issues": [], "codes": [], "warning_count": 0, "error_count": 0}

    for i in range(1, len(shots)):
        prev, cur = shots[i - 1], shots[i]
        pid = str(prev.get("id") or f"shot{i}")
        cid = str(cur.get("id") or f"shot{i + 1}")
        pair = [pid, cid]

        # 180° axis continuity: check look_axis flip without bridge/axis_break
        a0 = _axis_side(prev)
        a1 = _axis_side(cur)
        if a0 and a1 and a0 != a1 and a0 != "center" and a1 != "center":
            cur_fn = str(cur.get("dramatic_function") or "").strip().lower()
            if cur_fn != "bridge" and not cur.get("axis_break"):
                issues.append(
                    {
                        "code": CODE_AXIS_BREAK,
                        "level": "warning",
                        "message": f"180° axis flip: {pid} look_axis={a0!r} → {cid} look_axis={a1!r} without bridge/axis_break",
                        "shot_ids": pair,
                    }
                )

        # 30-degree rule: same shot_size in adjacent shots = too similar angle
        r0 = _size_rank(prev)
        r1 = _size_rank(cur)
        if r0 is not None and r1 is not None and r0 == r1:
            cur_fn = str(cur.get("dramatic_function") or "").strip().lower()
            if cur_fn not in {"bridge", "insert"}:
                issues.append(
                    {
                        "code": CODE_THIRTY_DEGREE_VIOLATION,
                        "level": "warning",
                        "message": f"30° rule: {pid} and {cid} same shot_size rank={r0} — change angle or size",
                        "shot_ids": pair,
                    }
                )

        # Eyeline match: if prev subject looks left, next subject should be on right
        e0 = _eyeline_target(prev)
        a1 = _axis_side(cur)
        if e0 and a1 and e0 != "center" and a1 != "center":
            if e0 == a1:
                issues.append(
                    {
                        "code": CODE_EYELINE_MISMATCH,
                        "level": "warning",
                        "message": f"eyeline mismatch: {pid} gaze={e0!r} but {cid} axis_side={a1!r} — counterpart should be on opposite side",
                        "shot_ids": pair,
                    }
                )

    # Size progression flat: 3+ consecutive same-size-band without variation
    for i in range(2, len(shots)):
        s0, s1, s2 = shots[i - 2], shots[i - 1], shots[i]
        r0, r1, r2 = _size_rank(s0), _size_rank(s1), _size_rank(s2)
        if r0 is not None and r0 == r1 == r2:
            issues.append(
                {
                    "code": CODE_SIZE_PROGRESSION_FLAT,
                    "level": "warning",
                    "message": f"3 consecutive shots same shot_size rank={r0} — vary size for visual rhythm",
                    "shot_ids": [str(s0.get("id")), str(s1.get("id")), str(s2.get("id"))],
                }
            )

    codes = sorted({str(i["code"]) for i in issues})
    warning_count = sum(1 for i in issues if i.get("level") == "warning")
    error_count = sum(1 for i in issues if i.get("level") == "error")
    return {
        "ok": warning_count == 0 and error_count == 0,
        "issues": issues,
        "codes": codes,
        "warning_count": warning_count,
        "error_count": error_count,
        "note": "P1-7: 180° axis / 30° rule / eyeline match / size progression. Soft by default.",
    }


def framing_crop_risk_in_text(text: str) -> list[str]:
    """Public helper for unit tests / still-prompt gates."""
    return _match_any(text or "", CROP_PRONE_PATTERNS)


def lint_vertical_safe_area(shots: list[dict[str, Any]]) -> dict[str, Any]:
    """Check that platform UI/subtitle/subject zones are declared for 9:16."""
    issues: list[dict[str, Any]] = []
    required = ("top_ui_clear", "subtitle_clear", "subject_clear", "prop_readable")
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        area = shot.get("safe_area") or dsl.get("safe_area")
        if not isinstance(area, dict):
            issues.append(
                {
                    "shot_id": str(shot.get("id") or "?"),
                    "code": "VERTICAL_SAFE_AREA_UNDECLARED",
                    "level": "warning",
                    "message": VERTICAL_SAFE_AREA_HINT,
                }
            )
            continue
        missing = [key for key in required if area.get(key) is not True]
        if missing:
            issues.append(
                {
                    "shot_id": str(shot.get("id") or "?"),
                    "code": "VERTICAL_SAFE_AREA_INCOMPLETE",
                    "level": "warning",
                    "missing": missing,
                    "message": f"missing safe-area declarations: {', '.join(missing)}",
                }
            )
    codes = sorted({str(i["code"]) for i in issues})
    return {"ok": not issues, "codes": codes, "warning_count": len(issues), "issues": issues}
