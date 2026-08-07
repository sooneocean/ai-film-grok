"""Pure helpers for render_final (orchestrator relief W1).

Dimension / plate-slot / optional float — no I/O, no policy retune.
"""

from __future__ import annotations


def resolve_render_dimension(*sources: object, default: int) -> int:
    """Resolve a render dimension with CLI > timeline > manifest > default fallback.

    Every source is coerced defensively so a non-numeric value degrades to the
    next fallback instead of raising mid-render.
    """
    for src in sources:
        if src in (None, "", 0):
            continue
        try:
            return int(src)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
    return default


def resolve_plate_slot_sec(
    shot: object,
    *,
    default: float = 1.0,
    min_sec: float = 0.05,
) -> float:
    """Resolve a plate clock duration from shot.duration_sec (pure helper).

    Invalid or missing values degrade to ``default``. Values at or below
    ``min_sec`` are treated as unusable.
    """
    try:
        raw = shot.get("duration_sec") if isinstance(shot, dict) else None
        plate_slot = float(raw or 0.0)
    except (TypeError, ValueError):
        plate_slot = 0.0
    if plate_slot <= min_sec:
        return float(default)
    return float(plate_slot)


def coerce_optional_float(value: object) -> float | None:
    """Coerce a present value to float; None stays None (conversion errors raise)."""
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]
