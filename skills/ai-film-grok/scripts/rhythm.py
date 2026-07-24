#!/usr/bin/env python3
"""Director-facing rhythm and coverage lint for short vertical episodes."""

from __future__ import annotations

from typing import Any

SHOT_SIZE_RANK = {
    "wide": 1,
    "long": 1,
    "establishing": 1,
    "medium": 2,
    "medium shot": 2,
    "medium close-up": 3,
    "close-up": 4,
    "close": 4,
    "extreme close-up": 5,
    "ecu": 5,
}


def _size_rank(shot: dict[str, Any]) -> int | None:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    camera = dsl.get("camera") if isinstance(dsl.get("camera"), dict) else {}
    raw = (
        str(shot.get("shotSize") or dsl.get("shot_size") or camera.get("shot_size") or "")
        .strip()
        .lower()
    )
    if raw in SHOT_SIZE_RANK:
        return SHOT_SIZE_RANK[raw]
    for key, rank in SHOT_SIZE_RANK.items():
        if key in raw:
            return rank
    return None


def lint_rhythm(
    shots: list[dict[str, Any]], *, target_duration: float | None = None
) -> dict[str, Any]:
    """Report hook timing, coverage repetition, size pressure and ending hook.

    This is advisory by default; ``rhythm_strict`` in film-spec promotes errors
    to a hard gate after the director has authored the intended grammar.
    """
    issues: list[dict[str, Any]] = []
    ordered = [s for s in shots if isinstance(s, dict)]
    if not ordered:
        return {"ok": False, "codes": ["RHYTHM_NO_SHOTS"], "issues": []}

    first_duration = float(ordered[0].get("duration_sec") or ordered[0].get("targetDuration") or 0)
    if first_duration > 3.5:
        issues.append(
            {
                "code": "RHYTHM_HOOK_LATE",
                "level": "warning",
                "shot_id": ordered[0].get("id"),
                "message": "第一镜超过 3.5 秒才完成钩子风险",
            }
        )

    by_beat: dict[str, list[dict[str, Any]]] = {}
    for shot in ordered:
        bid = str(shot.get("beat_id") or shot.get("beatId") or "unknown")
        by_beat.setdefault(bid, []).append(shot)
    for bid, group in by_beat.items():
        roles = [str(s.get("coverage_role") or "").strip().lower() for s in group]
        actions = [
            str(s.get("visible_change") or s.get("must_show") or "").strip().lower() for s in group
        ]
        if len(group) > 1 and len(set(roles)) == 1:
            issues.append(
                {
                    "code": "RHYTHM_COVERAGE_FLAT",
                    "level": "warning",
                    "node_ref": bid,
                    "message": "同一 Beat 的镜头覆盖功能没有变化",
                }
            )
        if len(group) > 1 and len(set(actions)) == 1:
            issues.append(
                {
                    "code": "RHYTHM_EVIDENCE_REPEAT",
                    "level": "warning",
                    "node_ref": bid,
                    "message": "同一 Beat 重复提供相同视觉证据",
                }
            )

    ranks = [_size_rank(s) for s in ordered]
    known = [r for r in ranks if r is not None]
    if len(known) >= 4 and max(known) == min(known):
        issues.append(
            {
                "code": "RHYTHM_SIZE_FLAT",
                "level": "warning",
                "message": "全片景别没有形成情绪压力阶梯",
            }
        )
    if ordered and str(ordered[-1].get("dramatic_function") or "").lower() not in {
        "afterglow",
        "bridge",
        "reaction",
    }:
        issues.append(
            {
                "code": "RHYTHM_NO_BUTTON",
                "level": "warning",
                "shot_id": ordered[-1].get("id"),
                "message": "结尾没有明确余波或下一集钩子功能",
            }
        )
    if (
        target_duration is not None
        and sum(float(s.get("duration_sec") or s.get("targetDuration") or 0) for s in ordered) <= 0
    ):
        issues.append(
            {"code": "RHYTHM_NO_TIMING", "level": "warning", "message": "镜头没有可用时长"}
        )

    codes = sorted({str(x.get("code")) for x in issues})
    return {"ok": not issues, "codes": codes, "warning_count": len(issues), "issues": issues}


def verify_pace_chart(
    shots: list[dict[str, Any]],
    pace_chart: list[dict[str, Any]] | list[str],
    *,
    total_duration: float | None = None,
) -> dict[str, Any]:
    """P4-extend: verify actual cut frequency matches declared pace_chart.

    Compares the declared pace_chart segments (start_ratio/end_ratio/cut_freq/intensity)
    against the actual shot timeline — measures cut frequency (shots per second)
    within each segment's time range.

    Returns {ok, issues, codes, warning_count, segments_checked}.
    """
    issues: list[dict[str, Any]] = []
    ordered = [s for s in shots if isinstance(s, dict)]
    if not ordered or not pace_chart:
        return {"ok": True, "issues": [], "codes": [], "warning_count": 0, "segments_checked": 0}

    # Calculate total duration
    if total_duration is None:
        total_duration = sum(
            float(s.get("duration_sec") or s.get("targetDuration") or 0) for s in ordered
        )
    if total_duration <= 0:
        total_duration = max(len(ordered) * 5.0, 30.0)  # fallback estimate

    # Build cumulative shot timeline
    shot_times: list[tuple[float, float]] = []
    cursor = 0.0
    for s in ordered:
        dur = float(s.get("duration_sec") or s.get("targetDuration") or 5.0)
        shot_times.append((cursor, cursor + dur))
        cursor += dur

    segments_checked = 0
    for i, entry in enumerate(pace_chart):
        if isinstance(entry, str):
            continue  # legacy string format — skip

        if not isinstance(entry, dict):
            continue

        sr = entry.get("start_ratio")
        er = entry.get("end_ratio")
        declared_freq = entry.get("cut_freq")
        label = str(entry.get("label") or f"segment_{i}")

        if sr is None or er is None:
            continue

        start_sec = float(sr) * total_duration
        end_sec = float(er) * total_duration

        # Count shots that start within this segment's time range
        shots_in_segment = [
            idx for idx, (s, e) in enumerate(shot_times) if s < end_sec and e > start_sec
        ]
        segment_duration = end_sec - start_sec
        if segment_duration <= 0:
            continue

        actual_freq = len(shots_in_segment) / segment_duration
        segments_checked += 1

        # Map declared cut_freq to expected range
        freq_ranges = {
            "slow": (0.0, 0.15),  # ≤1 shot per 6.5s
            "medium": (0.15, 0.3),  # ~1 shot per 3-6s
            "fast": (0.3, 0.6),  # ~1 shot per 1.5-3s
            "rapid": (0.6, 99.0),  # >1 shot per 1.5s
        }

        if declared_freq and declared_freq in freq_ranges:
            lo, hi = freq_ranges[declared_freq]
            if actual_freq < lo:
                issues.append(
                    {
                        "code": "PACE_CHART_TOO_SLOW",
                        "level": "warning",
                        "message": (
                            f"pace_chart segment '{label}': actual cut freq {actual_freq:.3f}/s "
                            f"is below declared '{declared_freq}' range [{lo:.2f}, {hi:.2f}]"
                        ),
                    }
                )
            elif actual_freq > hi:
                issues.append(
                    {
                        "code": "PACE_CHART_TOO_FAST",
                        "level": "warning",
                        "message": (
                            f"pace_chart segment '{label}': actual cut freq {actual_freq:.3f}/s "
                            f"exceeds declared '{declared_freq}' range [{lo:.2f}, {hi:.2f}]"
                        ),
                    }
                )

    codes = sorted({str(x.get("code")) for x in issues})
    return {
        "ok": not issues,
        "codes": codes,
        "warning_count": len(issues),
        "issues": issues,
        "segments_checked": segments_checked,
        "note": "P4-extend: verifies actual cut frequency vs declared pace_chart. Soft by default.",
    }


# Map dramatic_function to three-act structure
_ACT1_FUNCS = {"hook", "approach"}
_ACT2_FUNCS = {"sensory", "reaction", "action"}
_ACT3_FUNCS = {"afterglow", "bridge"}


def _shot_act(shot: dict[str, Any]) -> str:
    """Map a shot's dramatic_function to act 1/2/3."""
    df = str(shot.get("dramatic_function") or "").strip().lower()
    if df in _ACT1_FUNCS:
        return "setup"
    if df in _ACT2_FUNCS:
        return "confrontation"
    if df in _ACT3_FUNCS:
        return "resolution"
    return "setup"  # default


def verify_act_structure(
    shots: list[dict[str, Any]],
    act_structure: dict[str, Any],
    *,
    total_duration: float | None = None,
    tolerance: float = 0.10,
) -> dict[str, Any]:
    """Verify actual act proportions match declared act_structure ratios.

    Compares declared setup_ratio/confrontation_ratio/resolution_ratio against
    the actual proportion of total duration spent in each act (mapped via
    dramatic_function).

    Returns {ok, issues, codes, warning_count, actual_ratios}.
    """
    issues: list[dict[str, Any]] = []
    ordered = [s for s in shots if isinstance(s, dict)]
    if not ordered or not act_structure:
        return {"ok": True, "issues": [], "codes": [], "warning_count": 0, "actual_ratios": {}}

    if total_duration is None:
        total_duration = sum(
            float(s.get("duration_sec") or s.get("targetDuration") or 0) for s in ordered
        )
    if total_duration <= 0:
        total_duration = max(len(ordered) * 5.0, 30.0)

    # Calculate actual act durations
    act_durations: dict[str, float] = {"setup": 0.0, "confrontation": 0.0, "resolution": 0.0}
    for s in ordered:
        dur = float(s.get("duration_sec") or s.get("targetDuration") or 5.0)
        act = _shot_act(s)
        act_durations[act] += dur

    actual_ratios = {k: v / total_duration for k, v in act_durations.items()}

    # Compare with declared ratios
    declared_map = {
        "setup": act_structure.get("setup_ratio"),
        "confrontation": act_structure.get("confrontation_ratio"),
        "resolution": act_structure.get("resolution_ratio"),
    }

    for act_name, declared in declared_map.items():
        if declared is None:
            continue
        declared_f = float(declared)
        actual_f = actual_ratios[act_name]
        delta = abs(actual_f - declared_f)
        if delta > tolerance:
            direction = "over" if actual_f > declared_f else "under"
            issues.append(
                {
                    "code": "ACT_RATIO_MISMATCH",
                    "level": "warning",
                    "message": (
                        f"act_structure.{act_name}_ratio: declared={declared_f:.2f} "
                        f"but actual={actual_f:.2f} (Δ={delta:.2f}, {direction} by tolerance {tolerance:.2f})"
                    ),
                }
            )

    codes = sorted({str(x.get("code")) for x in issues})
    return {
        "ok": not issues,
        "codes": codes,
        "warning_count": len(issues),
        "issues": issues,
        "actual_ratios": actual_ratios,
        "note": "Verifies actual act proportions vs declared act_structure ratios. Soft by default.",
    }


def verify_music_spotting(
    music_spotting: list[dict[str, Any]],
    beats: list[dict[str, Any]] | None = None,
    *,
    total_duration: float | None = None,
) -> dict[str, Any]:
    """Verify BGM spotting entries align with declared beats.

    Checks:
    - Each music_spotting entry with beat_ref references a valid beat id
    - Music segments don't overlap
    - start_sec < end_sec for each segment
    - Segments fit within total duration

    Returns {ok, issues, codes, warning_count, segments_checked}.
    """
    issues: list[dict[str, Any]] = []
    if not music_spotting:
        return {"ok": True, "issues": [], "codes": [], "warning_count": 0, "segments_checked": 0}

    beat_ids: set[str] = set()
    if beats:
        for bt in beats:
            if isinstance(bt, dict):
                bid = str(bt.get("id") or "").strip()
                if bid:
                    beat_ids.add(bid)

    segments_checked = 0
    prev_end = 0.0
    for i, entry in enumerate(music_spotting):
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or f"segment_{i}")
        start = entry.get("start_sec")
        end = entry.get("end_sec")
        beat_ref = entry.get("beat_ref")

        segments_checked += 1

        # start < end
        if start is not None and end is not None:
            if float(end) <= float(start):
                issues.append(
                    {
                        "code": "MUSIC_SPOT_INVALID_RANGE",
                        "level": "warning",
                        "message": f"music_spotting '{label}': end_sec={end} must be > start_sec={start}",
                    }
                )

        # Total duration boundary
        if total_duration and start is not None:
            if float(start) < 0 or (end is not None and float(end) > total_duration):
                issues.append(
                    {
                        "code": "MUSIC_SPOT_OUT_OF_RANGE",
                        "level": "warning",
                        "message": f"music_spotting '{label}': segment extends beyond total_duration={total_duration}",
                    }
                )

        # Beat ref validity
        if beat_ref and beat_ids:
            if str(beat_ref).strip() not in beat_ids:
                issues.append(
                    {
                        "code": "MUSIC_SPOT_BEAT_REF_INVALID",
                        "level": "warning",
                        "message": f"music_spotting '{label}': beat_ref='{beat_ref}' not found in beats",
                    }
                )

        # Overlap check
        if start is not None and float(start) < prev_end - 0.01:
            issues.append(
                {
                    "code": "MUSIC_SPOT_OVERLAP",
                    "level": "warning",
                    "message": f"music_spotting '{label}': starts at {start} but previous segment ends at {prev_end} — overlap",
                }
            )
        if end is not None:
            prev_end = max(prev_end, float(end))

    codes = sorted({str(x.get("code")) for x in issues})
    return {
        "ok": not issues,
        "codes": codes,
        "warning_count": len(issues),
        "issues": issues,
        "segments_checked": segments_checked,
        "note": "Verifies BGM spotting alignment with beats. Soft by default.",
    }
