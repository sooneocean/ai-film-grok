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
