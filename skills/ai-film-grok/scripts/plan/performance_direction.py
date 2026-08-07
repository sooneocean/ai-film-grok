"""Acting direction beyond emotion labels (Film Production OS W7).

Not only angry/sad/happy — include objective, subtext, intensity, tempo,
body language, eye behavior, breathing, speech rhythm.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, utc_now, write_json

CODE_PERF_EMOTION_ONLY = "PERFORMANCE_EMOTION_ONLY"
CODE_PERF_EMPTY = "PERFORMANCE_EMPTY"

_EMOTION_ONLY_MARKERS = frozenset(
    {
        "angry",
        "sad",
        "happy",
        "scared",
        "fear",
        "fearful",
        "neutral",
        "calm",
        "生气",
        "难过",
        "开心",
        "害怕",
        "平静",
    }
)


def _text(value: object) -> str:
    return str(value or "").strip()


def _blank(value: object) -> bool:
    return not _text(value)


def normalize_performance_direction(raw: object = None) -> dict[str, Any]:
    """Normalize a full performance direction object (provider-neutral)."""
    src = raw if isinstance(raw, dict) else {}
    intensity = src.get("intensity")
    try:
        intensity_f = float(intensity) if intensity is not None else None
    except (TypeError, ValueError):
        intensity_f = None
    if intensity_f is not None:
        intensity_f = max(0.0, min(1.0, intensity_f))

    return {
        "schema_version": 1,
        "kind": "performance-direction",
        "objective": _text(src.get("objective")) or None,
        "subtext": _text(src.get("subtext")) or None,
        "emotion": _text(src.get("emotion") or src.get("emotional_state")) or None,
        "outward_expression": _text(src.get("outward_expression")) or None,
        "intensity": intensity_f,
        "tempo": _text(src.get("tempo") or src.get("speech_rhythm")) or None,
        "body_language": _text(src.get("body_language")) or None,
        "eye_behavior": _text(src.get("eye_behavior")) or None,
        "breathing": _text(src.get("breathing")) or None,
        "dialogue_delivery": _text(src.get("dialogue_delivery")) or None,
        "reaction_timing": _text(src.get("reaction_timing")) or None,
    }


def compile_performance_instruction(direction: dict[str, Any]) -> str:
    """Human + model-facing performance instruction (not a vibe word)."""
    d = normalize_performance_direction(direction)
    parts: list[str] = []
    if d.get("objective"):
        parts.append(f"Objective: {d['objective']}")
    if d.get("subtext"):
        parts.append(f"Subtext: {d['subtext']}")
    if d.get("emotion"):
        expr = d.get("outward_expression") or "as written"
        parts.append(f"Emotion: {d['emotion']} (outward: {expr})")
    if d.get("intensity") is not None:
        parts.append(f"Intensity: {d['intensity']:.2f}")
    if d.get("body_language"):
        parts.append(f"Body: {d['body_language']}")
    if d.get("eye_behavior"):
        parts.append(f"Eyes: {d['eye_behavior']}")
    if d.get("breathing"):
        parts.append(f"Breath: {d['breathing']}")
    if d.get("tempo"):
        parts.append(f"Tempo: {d['tempo']}")
    if d.get("dialogue_delivery"):
        parts.append(f"Delivery: {d['dialogue_delivery']}")
    if d.get("reaction_timing"):
        parts.append(f"Reaction timing: {d['reaction_timing']}")
    return "; ".join(parts) if parts else "Performance: natural, motivated, no empty emotion label."


def lint_performance_direction(
    shot: dict[str, Any],
    *,
    strict: bool = False,
) -> dict[str, Any]:
    """Flag shots that only have a bare emotion label or no direction at all."""
    sid = _text(shot.get("id") or "shot")
    issues: list[dict[str, Any]] = []
    perf = shot.get("performance") if isinstance(shot.get("performance"), dict) else {}
    direction = shot.get("performance_direction")
    if not isinstance(direction, dict):
        direction = perf if perf else {}
    # vocal cue alone does not count as full acting direction
    has_rich = any(
        not _blank(direction.get(k))
        for k in (
            "objective",
            "subtext",
            "body_language",
            "eye_behavior",
            "breathing",
            "outward_expression",
        )
    )
    emotion = _text(direction.get("emotion") or shot.get("emotion") or "")
    if not has_rich and not emotion and not direction:
        issues.append(
            {
                "code": CODE_PERF_EMPTY,
                "severity": "warning",
                "message": f"{sid}: no performance direction (objective/subtext/body/eye…)",
                "shot_ids": [sid],
            }
        )
    elif emotion and emotion.lower() in _EMOTION_ONLY_MARKERS and not has_rich:
        issues.append(
            {
                "code": CODE_PERF_EMOTION_ONLY,
                "severity": "error" if strict else "warning",
                "message": (
                    f"{sid}: performance reduced to emotion label {emotion!r} — "
                    "add objective/subtext/body/eye/breath"
                ),
                "shot_ids": [sid],
            }
        )
    errors = [i for i in issues if i.get("severity") == "error"]
    return {
        "ok": not errors,
        "shot_id": sid,
        "issues": issues,
        "codes": sorted({str(i["code"]) for i in issues}),
        "instruction": compile_performance_instruction(direction) if direction else None,
        "normalized": normalize_performance_direction(direction) if direction else None,
    }


def lint_spec_performance(
    spec: dict[str, Any],
    *,
    strict: bool = False,
) -> dict[str, Any]:
    shots: list[dict[str, Any]] = []
    for sc in spec.get("scenes") or []:
        if not isinstance(sc, dict):
            continue
        for sh in sc.get("shots") or []:
            if isinstance(sh, dict):
                shots.append(sh)
        for beat in sc.get("beats") or []:
            if not isinstance(beat, dict):
                continue
            for sh in beat.get("shots") or []:
                if isinstance(sh, dict):
                    shots.append(sh)
    reports = [lint_performance_direction(s, strict=strict) for s in shots]
    all_issues: list[dict[str, Any]] = []
    for r in reports:
        all_issues.extend(r.get("issues") or [])
    errors = [i for i in all_issues if i.get("severity") == "error"]
    return {
        "ok": not errors,
        "kind": "performance-direction",
        "strict": strict,
        "shot_count": len(shots),
        "issues": all_issues,
        "codes": sorted({str(i["code"]) for i in all_issues}),
        "shots": reports,
    }


def performance_direction_at_root(
    root: Path | str,
    *,
    strict: bool = False,
    write_receipt: bool = True,
) -> dict[str, Any]:
    root_p = Path(root).expanduser().resolve()
    spec = read_json(root_p / "film-spec.json") or {}
    if not isinstance(spec, dict):
        return {"ok": False, "error": "film-spec missing"}
    report = lint_spec_performance(spec, strict=strict)
    report["root"] = str(root_p)
    report["at"] = utc_now()
    if write_receipt:
        path = root_p / "receipts" / "performance-direction.json"
        write_json(path, report)
        report["receipt"] = str(path)
    return report
