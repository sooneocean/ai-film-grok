#!/usr/bin/env python3
"""Color grading path (ASC CDL) — bridges video-use grade.py to ai-film-grok.

video-use's grade model is ASC CDL per channel:
    out = (in * slope + offset) ** power, then global saturation.

Per-segment application during extraction (not post-concat, which double-encodes).
This module builds the ffmpeg filter chain string + a per-shot grade plan from
film-spec, so the edit pipeline can apply grades deterministically.

Pure logic — no ffmpeg execution here (the render layer calls ffmpeg).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from util import read_json, write_json


class ColorGradeError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


# Preset grade profiles (slopes/offsets/power per RGB channel + saturation).
# Adapted from video-use grade.py presets. Values are starting points, not mandates.
PRESETS: dict[str, dict[str, Any]] = {
    "none": {
        "label": "无调色（直通）",
        "slope": [1.0, 1.0, 1.0],
        "offset": [0.0, 0.0, 0.0],
        "power": [1.0, 1.0, 1.0],
        "saturation": 1.0,
    },
    "warm_cinematic": {
        "label": "暖色电影感（青橙互补，微降饱）",
        "slope": [1.05, 1.02, 0.95],
        "offset": [0.01, 0.0, -0.02],
        "power": [1.0, 1.0, 1.0],
        "saturation": 0.9,
    },
    "neutral_punch": {
        "label": "中性增强（对比微抬，无偏色）",
        "slope": [1.04, 1.04, 1.04],
        "offset": [-0.01, -0.01, -0.01],
        "power": [0.98, 0.98, 0.98],
        "saturation": 1.05,
    },
    "cool_steel": {
        "label": "冷钢蓝（偏青蓝，疏离清冷）",
        "slope": [0.95, 0.98, 1.08],
        "offset": [-0.02, 0.0, 0.02],
        "power": [1.0, 1.0, 1.0],
        "saturation": 0.92,
    },
    "high_contrast": {
        "label": "高反差（黑白场分明）",
        "slope": [1.1, 1.1, 1.1],
        "offset": [-0.03, -0.03, -0.03],
        "power": [0.92, 0.92, 0.92],
        "saturation": 1.0,
    },
    "pastel_soft": {
        "label": "柔和粉彩（低对比柔色）",
        "slope": [0.98, 0.98, 0.98],
        "offset": [0.02, 0.02, 0.02],
        "power": [1.05, 1.05, 1.05],
        "saturation": 0.85,
    },
}


def list_presets() -> list[str]:
    return list(PRESETS)


def _fmt_channel(slope: float, offset: float, power: float, rgb: str) -> str:
    """ffmpeg colorchannelmixer token for one channel."""
    # colorchannelmixer uses gain (slope); offset via curves; power via gamma.
    # For a single combined chain we use eq + colorbalance approximation.
    return f"{rgb}={slope}:{offset}:{power}"


def build_ffmpeg_filter(grade: str | dict[str, Any]) -> str:
    """Build an ffmpeg filter chain string for a grade preset or raw CDL.

    For preset names → eq + colorbalance approximation of ASC CDL.
    For raw ffmpeg filter strings (starting with a known filter name) → passthrough.
    """
    if isinstance(grade, str):
        if grade in PRESETS:
            preset = PRESETS[grade]
        elif grade.startswith(("eq=", "colorbalance=", "curves=", "lutyuv=", "lutrgb=")):
            return grade  # raw ffmpeg filter passthrough
        else:
            raise ColorGradeError(f"unknown grade preset: {grade}")
    elif isinstance(grade, dict):
        preset = grade
    else:
        raise ColorGradeError(f"grade must be str preset or dict, got {type(grade)}")

    s = preset["slope"]
    o = preset["offset"]
    p = preset["power"]
    sat = preset["saturation"]

    # eq filter: contrast≈avg slope, brightness≈avg offset, gamma≈avg power, saturation=sat
    avg_slope = sum(s) / 3.0
    avg_offset = sum(o) / 3.0
    avg_power = sum(p) / 3.0
    contrast = avg_slope
    brightness = avg_offset
    gamma = 1.0 / avg_power if avg_power > 0 else 1.0

    chain = f"eq=contrast={contrast:.4f}:brightness={brightness:.4f}:gamma={gamma:.4f}:saturation={sat:.4f}"

    # colorbalance for per-channel tint (offset approximation)
    if abs(o[0] - o[2]) > 0.005 or abs(o[1] - o[2]) > 0.005:
        rs = max(-1.0, min(1.0, o[0] * 2))
        gs = max(-1.0, min(1.0, o[1] * 2))
        bs = max(-1.0, min(1.0, o[2] * 2))
        chain += f",colorbalance=rs={rs:.4f}:gs={gs:.4f}:bs={bs:.4f}"

    return chain


def plan_shot_grades(root: Path | str) -> dict[str, Any]:
    """Walk film-spec.json and build a per-shot grade plan.

    Reads each shot's ``dsl.palette`` (set by cinema_prompt) and maps it to a
    grade preset. Writes a receipt at ``receipts/color-grade-plan.json``.
    """
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json")
    if not spec:
        raise ColorGradeError(f"film-spec.json not found or invalid in {root}")

    # palette → preset mapping (palette keys from cinema_prompt VISUAL_STYLES)
    palette_to_preset = {
        "teal_orange": "warm_cinematic",
        "desaturated": "neutral_punch",
        "warm_amber": "warm_cinematic",
        "cool_steel": "cool_steel",
        "high_contrast": "high_contrast",
        "pastel": "pastel_soft",
        "clean": "none",
    }

    # heat_phase → grade preset fallback (drives narrative color arc when no
    # explicit palette is set). Derived from visual_bible.LIGHTING_COLOR_PALETTES.
    # P1-9: previously derive_lighting_timeline was orphan code with no callers.
    heat_phase_to_preset = {
        "setup": "none",
        "teaser": "warm_cinematic",
        "foreplay": "warm_cinematic",
        "act": "high_contrast",
        "climax": "high_contrast",
        "afterglow": "warm_cinematic",
    }

    # Derive lighting timeline from heat_phase for shots without explicit palette.
    # This connects the narrative lighting arc to the color grade pipeline.
    all_shots_raw: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict):
                all_shots_raw.append(shot)

    lighting_timeline: list[dict[str, Any]] = []
    try:
        from visual_bible import derive_lighting_timeline

        lighting_timeline = derive_lighting_timeline(all_shots_raw)
    except Exception:
        pass
    lighting_by_shot: dict[str, dict[str, Any]] = {
        str(t.get("shot_id")): t for t in lighting_timeline if isinstance(t, dict)
    }

    shots: list[dict[str, Any]] = []
    for shot in all_shots_raw:
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        palette = str(dsl.get("palette") or "").strip().lower()
        sid = str(shot.get("id") or "")
        lt = lighting_by_shot.get(sid) or {}

        if palette:
            preset = palette_to_preset.get(palette, "none")
            source = "palette"
        else:
            # Fallback: derive from heat-phase lighting timeline (narrative color arc)
            hp = str(lt.get("heat_phase") or shot.get("heat_phase") or "").strip().lower()
            preset = heat_phase_to_preset.get(hp, "none")
            source = f"lighting_timeline:{hp}" if hp else "default"

        shots.append(
            {
                "shot_id": shot.get("id"),
                "palette": palette or None,
                "grade_preset": preset,
                "filter": build_ffmpeg_filter(preset),
                "lighting_theme": lt.get("lighting_theme"),
                "lighting_source": source,
            }
        )

    receipt = {
        "schema_version": 1,
        "kind": "color-grade-plan",
        "ok": True,
        "shots": shots,
        "presets_available": list_presets(),
        "created_at": utc_now(),
        "note": "Per-shot ASC CDL grade plan: explicit dsl.palette → preset; "
        "fallback to heat-phase lighting timeline (narrative color arc). "
        "Apply per-segment during extraction (video-use Hard Rule).",
    }
    out = root / "receipts" / "color-grade-plan.json"
    write_json(out, receipt)
    receipt["path"] = str(out)
    return receipt
