"""Target duration honesty (Q4.1 · savani H3 native review).

H3 clips are typically ~5.0–5.3s. Planning N×5s must not silently ship
a film 20%+ shorter than target_duration without a clear next action.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

# Default H3 single-clip generation length (seconds) used for shot-count advice.
H3_NOMINAL_CLIP_SEC = 5.2
# Soft: warn; Hard: fail when gap exceeds this fraction of target.
DEFAULT_SOFT_GAP_RATIO = 0.12
DEFAULT_HARD_GAP_RATIO = 0.20


def flatten_shots(spec: dict[str, Any] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(spec, dict):
        return out
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for sh in scene.get("shots") or []:
            if isinstance(sh, dict):
                out.append(sh)
    if not out and isinstance(spec.get("shots"), list):
        for sh in spec["shots"]:
            if isinstance(sh, dict):
                out.append(sh)
    return out


def resolve_target_duration_sec(spec: dict[str, Any] | None) -> float | None:
    """Pick target from common film-spec keys."""
    if not isinstance(spec, dict):
        return None
    for key in (
        "target_duration",
        "target_duration_sec",
        "targetDuration",
        "targetDurationSec",
    ):
        raw = spec.get(key)
        if raw is None:
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if v > 0:
            return v
    longform = spec.get("longform_profile") if isinstance(spec.get("longform_profile"), dict) else {}
    raw = longform.get("target_duration_sec")
    if raw is not None:
        try:
            v = float(raw)
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass
    return None


def planned_sum_duration_sec(shots: list[dict[str, Any]]) -> float:
    total = 0.0
    for sh in shots:
        try:
            total += float(sh.get("duration_sec") or 0.0)
        except (TypeError, ValueError):
            continue
    return total


def suggest_min_shots(target_sec: float, *, nominal_clip_sec: float = H3_NOMINAL_CLIP_SEC) -> int:
    if target_sec <= 0 or nominal_clip_sec <= 0:
        return 0
    return max(1, int(math.ceil(target_sec / nominal_clip_sec)))


def check_duration_target(
    spec: dict[str, Any] | None,
    *,
    soft_gap_ratio: float = DEFAULT_SOFT_GAP_RATIO,
    hard_gap_ratio: float = DEFAULT_HARD_GAP_RATIO,
    nominal_clip_sec: float = H3_NOMINAL_CLIP_SEC,
    media_sum_sec: float | None = None,
    strict: bool | None = None,
) -> dict[str, Any]:
    """Compare planned (and optional media) duration against target.

    Returns a report with ok / severity / codes / next actions.
    Does not mutate the spec.
    """
    target = resolve_target_duration_sec(spec)
    shots = flatten_shots(spec)
    planned = planned_sum_duration_sec(shots)
    n = len(shots)
    min_shots = suggest_min_shots(target or 0.0, nominal_clip_sec=nominal_clip_sec) if target else 0

    report: dict[str, Any] = {
        "schema_version": 1,
        "kind": "duration_target",
        "ok": True,
        "severity": "ok",
        "codes": [],
        "target_duration_sec": target,
        "planned_sum_sec": round(planned, 3),
        "media_sum_sec": None if media_sum_sec is None else round(float(media_sum_sec), 3),
        "shot_count": n,
        "suggested_min_shots_h3": min_shots,
        "nominal_clip_sec": nominal_clip_sec,
        "gap_planned_sec": None,
        "gap_planned_ratio": None,
        "gap_media_sec": None,
        "gap_media_ratio": None,
        "next": [],
        "message": "",
    }

    if target is None or target <= 0:
        report["ok"] = True
        report["severity"] = "skip"
        report["codes"] = ["DURATION_TARGET_UNSET"]
        report["message"] = "no target_duration on film-spec; skip honesty check"
        return report

    if n == 0:
        report["ok"] = False
        report["severity"] = "hard"
        report["codes"] = ["DURATION_NO_SHOTS"]
        report["message"] = "target set but no shots"
        report["next"] = ["plan run / write-spec: add shots"]
        return report

    gap = target - planned
    ratio = gap / target if target else 0.0
    report["gap_planned_sec"] = round(gap, 3)
    report["gap_planned_ratio"] = round(ratio, 4)

    codes: list[str] = []
    nexts: list[str] = []
    severity = "ok"

    if ratio > hard_gap_ratio:
        codes.append("DURATION_TARGET_SHORT_HARD")
        severity = "hard"
        nexts.extend(
            [
                f"add ~{max(1, min_shots - n)} shots (H3 ~{nominal_clip_sec}s each) "
                f"or raise FLF/duration so planned≥{target:.0f}s",
                f"or lower target_duration to ~{planned:.0f}s and re-lock promise",
                "do not silent-deliver short plate as full target",
            ]
        )
    elif ratio > soft_gap_ratio:
        codes.append("DURATION_TARGET_SHORT_SOFT")
        severity = "soft"
        nexts.append(
            f"planned {planned:.1f}s is {ratio * 100:.0f}% under target {target:.0f}s — "
            f"suggest ≥{min_shots} shots at ~{nominal_clip_sec}s"
        )
    elif gap < -target * soft_gap_ratio:
        codes.append("DURATION_TARGET_OVER_SOFT")
        severity = "soft"
        nexts.append(
            f"planned {planned:.1f}s exceeds target {target:.0f}s — trim or raise target"
        )

    if media_sum_sec is not None and media_sum_sec > 0:
        mgap = target - float(media_sum_sec)
        mratio = mgap / target
        report["gap_media_sec"] = round(mgap, 3)
        report["gap_media_ratio"] = round(mratio, 4)
        if mratio > hard_gap_ratio:
            codes.append("DURATION_MEDIA_SHORT_HARD")
            if severity != "hard":
                severity = "hard"
            nexts.append(
                f"sum(approved clip dur)={media_sum_sec:.1f}s under target — "
                "re-I2V longer / add shots / FLF"
            )
        elif mratio > soft_gap_ratio:
            codes.append("DURATION_MEDIA_SHORT_SOFT")
            if severity == "ok":
                severity = "soft"

    # strict override from spec
    if strict is None and isinstance(spec, dict):
        raw = spec.get("duration_target_strict")
        if raw is None:
            raw = (spec.get("delivery") or {}).get("duration_target_strict") if isinstance(
                spec.get("delivery"), dict
            ) else None
        if raw is True:
            strict = True
        elif raw is False:
            strict = False

    if strict is True and severity == "soft" and any(
        c.endswith("_SOFT") for c in codes
    ):
        severity = "hard"
        codes.append("DURATION_TARGET_STRICT")

    ok = severity != "hard"
    report["ok"] = ok
    report["severity"] = severity
    report["codes"] = codes
    report["next"] = nexts
    if not codes:
        media_bit = (
            f"; media {media_sum_sec:.1f}s"
            if media_sum_sec is not None
            else ""
        )
        report["message"] = (
            f"planned {planned:.1f}s vs target {target:.1f}s "
            f"(gap {gap:+.1f}s){media_bit} ok"
        )
    else:
        media_bit = (
            f"; media {media_sum_sec:.1f}s"
            if media_sum_sec is not None
            else ""
        )
        report["message"] = (
            f"planned {planned:.1f}s vs target {target:.1f}s "
            f"(gap {gap:+.1f}s / {ratio * 100:.0f}%){media_bit} codes={codes}"
        )
    return report


def write_duration_target_receipt(
    root: Path | str,
    report: dict[str, Any],
    *,
    name: str = "duration-target.json",
) -> Path:
    from util import write_json

    root_p = Path(root).expanduser().resolve()
    path = root_p / "receipts" / name
    write_json(path, report)
    return path
