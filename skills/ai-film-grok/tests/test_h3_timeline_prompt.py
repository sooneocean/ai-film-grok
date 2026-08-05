"""H3 Layer-4 timeline prompt compiler unit tests."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from h3_timeline_prompt import (  # noqa: E402
    format_timecode,
    plan_segment_bounds,
    resolve_duration_sec,
    segment_count_for,
    validate_timeline_coverage,
)


def test_plan_segment_bounds_no_gaps() -> None:
    bounds = plan_segment_bounds(8, 3)
    assert bounds[0][0] == 0.0
    assert bounds[-1][1] == 8.0
    for i in range(len(bounds) - 1):
        assert bounds[i][1] == bounds[i + 1][0]


def test_segment_count_density_guide() -> None:
    assert 2 <= segment_count_for(5, prompt_tier="medium") <= 3
    assert 3 <= segment_count_for(8, prompt_tier="medium") <= 4
    assert segment_count_for(5, prompt_tier="soft") <= segment_count_for(
        5, prompt_tier="high"
    )


def test_resolve_duration_from_shot() -> None:
    assert resolve_duration_sec({"duration_sec": 6}) == 6.0
    assert resolve_duration_sec({"dsl": {"duration_sec": 4}}) == 4.0


def test_validate_timeline_ok() -> None:
    text = "\n".join(
        [
            f"{format_timecode(0, 3)} walk begins.",
            f"{format_timecode(3, 6)} walk continues.",
            f"{format_timecode(6, 8)} holds end pose.",
        ]
    )
    r = validate_timeline_coverage(text, duration_sec=8)
    assert r["ok"] is True
    assert r["segment_count"] == 3


def test_validate_timeline_gap_detected() -> None:
    text = "[0s-2s] a.\n[4s-6s] b."
    r = validate_timeline_coverage(text)
    assert r["ok"] is False
    assert r["error"] and "GAP" in r["error"]
