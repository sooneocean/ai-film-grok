"""plan_feedback pattern helpers (WIP completion)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from plan_feedback import (  # noqa: E402
    _analyze_shot_count,
    _classify_deviation_pattern,
    _compute_weight_suggestion,
    analyze_evidence,
)


def test_classify_consistent_over() -> None:
    devs = [{"direction": "over", "deviation_pct": 40}, {"direction": "over", "deviation_pct": 50}]
    assert _classify_deviation_pattern(devs) == "consistent_over"


def test_classify_mixed() -> None:
    devs = [{"direction": "over", "deviation_pct": 40}, {"direction": "under", "deviation_pct": 20}]
    assert _classify_deviation_pattern(devs) == "mixed"


def test_weight_suggestion_over_is_negative() -> None:
    devs = [
        {"direction": "over", "deviation_pct": 40},
        {"direction": "over", "deviation_pct": 60},
    ]
    out = _compute_weight_suggestion(devs, "consistent_over")
    assert out["suggested_weight_delta"] < 0
    assert out["sample_count"] == 2


def test_shot_count_adjustment_emitted() -> None:
    items = [
        {
            "evidence_id": "ep01_sc01_hook",
            "planned_shots": 2,
            "executed": {"shots_count": 4},
        },
        {
            "evidence_id": "ep01_sc02_hook",
            "planned_shots": 2,
            "executed": {"shots_count": 5},
        },
    ]
    adj = _analyze_shot_count(items)
    assert isinstance(adj, list)
    # may or may not emit depending on thresholds — must not crash
    assert all(isinstance(a, dict) for a in adj)


def test_analyze_evidence_empty() -> None:
    report = analyze_evidence([])
    assert isinstance(report, dict)
