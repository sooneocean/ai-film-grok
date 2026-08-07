"""Sex duration floor gate for film-spec validate (peeled · A1 2026-08-06).

Never silently pads act/climax duration_sec to invent stretchable slots.
"""

from __future__ import annotations

from typing import Any


class SexFloorError(ValueError):
    """Raised when sex duration floor fails in strict mode."""


def apply_sex_duration_floor(
    heat_rep: dict[str, Any],
    *,
    sex_floor_strict: bool,
    heat_scale: str = "max",
) -> None:
    """Fail-closed on HEAT_SEX_DURATION_LOW when strict (default max / explicit_max).

    Call after lint_heat_arc. Does **not** mutate shot durations.
    Plot-driven hot sets sex_floor_strict=False at project time, so this no-ops.
    """
    if not sex_floor_strict:
        return
    codes = heat_rep.get("codes") or []
    if "HEAT_SEX_DURATION_LOW" not in codes:
        return
    ratio = heat_rep.get("sex_duration_ratio")
    floor = heat_rep.get("sex_duration_floor")
    raise SexFloorError(
        "sex duration floor failed (sex_floor_strict): HEAT_SEX_DURATION_LOW "
        f"sex_duration_ratio={ratio} floor={floor} — "
        "next: (1) re-I2V longer takes, or (2) add act/climax shots so real "
        "media share meets floor, or (3) lower sex_min_duration_ratio / "
        "sex_floor_strict:false after intentional PARTIAL. "
        "Do NOT invent duration_sec=10 without matching source length "
        "(short H3 stretch cap ~5.9s). See memory 2026-08-06-suse-ep01-official-final-iron."
    )


def resolve_sex_floor_strict(spec: dict[str, Any], heat_scale: str) -> bool:
    """Default sex_floor_strict=True when heat_scale is max (explicit max IRON)."""
    raw = spec.get("sex_floor_strict")
    if raw is None:
        return str(heat_scale or "").strip().lower() == "max"
    return bool(raw)
