"""Tests for pace_chart verification — actual cut frequency vs declared curve.

Verifies:
- PACE_CHART_TOO_SLOW: actual cut freq below declared range
- PACE_CHART_TOO_FAST: actual cut freq exceeds declared range
- No issue when actual matches declared
- Legacy string pace_chart entries are skipped gracefully
- Empty pace_chart or shots → ok
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from rhythm import verify_pace_chart


class TestPaceChartVerification:
    """verify_pace_chart checks actual cut frequency vs declared."""

    def test_too_slow_detected(self):
        """Declared 'rapid' but only 1 shot in segment → too slow."""
        shots = [{"id": f"s{i}", "duration_sec": 5.0} for i in range(6)]
        pace = [
            {"label": "slow", "start_ratio": 0.0, "end_ratio": 0.3, "cut_freq": "slow"},
            {"label": "fast", "start_ratio": 0.3, "end_ratio": 0.7, "cut_freq": "rapid"},
            {"label": "release", "start_ratio": 0.7, "end_ratio": 1.0, "cut_freq": "slow"},
        ]
        result = verify_pace_chart(shots, pace, total_duration=30.0)
        # 30s total, 6 shots at 5s each = 0.2/s globally
        # In the "rapid" segment (9-21s), there are ~2-3 shots = 0.2-0.3/s
        # That's below "rapid" range [0.6, 99]
        assert "PACE_CHART_TOO_SLOW" in result["codes"]

    def test_too_fast_detected(self):
        """Declared 'slow' but many shots in segment → too fast."""
        shots = [{"id": f"s{i}", "duration_sec": 1.0} for i in range(30)]
        pace = [
            {"label": "build", "start_ratio": 0.0, "end_ratio": 0.5, "cut_freq": "slow"},
            {"label": "climax", "start_ratio": 0.5, "end_ratio": 1.0, "cut_freq": "fast"},
        ]
        result = verify_pace_chart(shots, pace, total_duration=30.0)
        # 30s total, 30 shots at 1s each = 1.0/s
        # In "slow" segment (0-15s), 15 shots = 1.0/s → exceeds slow range [0, 0.15]
        assert "PACE_CHART_TOO_FAST" in result["codes"]

    def test_matching_freq_no_issue(self):
        """When actual matches declared, no issue."""
        # 4 shots in 30s = 0.133/s — within slow range [0, 0.15]
        shots = [{"id": f"s{i}", "duration_sec": 7.5} for i in range(4)]
        pace = [
            {"label": "steady", "start_ratio": 0.0, "end_ratio": 1.0, "cut_freq": "slow"},
        ]
        result = verify_pace_chart(shots, pace, total_duration=30.0)
        assert result["ok"] is True

    def test_legacy_string_entries_skipped(self):
        """Legacy string pace_chart entries are gracefully skipped."""
        shots = [{"id": "s1", "duration_sec": 5.0}]
        pace = ["慢燃", "加速", "高潮", "释放"]
        result = verify_pace_chart(shots, pace)
        assert result["ok"] is True
        assert result["segments_checked"] == 0

    def test_empty_shots_ok(self):
        result = verify_pace_chart([], [{"label": "x", "start_ratio": 0.0, "end_ratio": 1.0}])
        assert result["ok"] is True

    def test_empty_pace_chart_ok(self):
        shots = [{"id": "s1", "duration_sec": 5.0}]
        result = verify_pace_chart(shots, [])
        assert result["ok"] is True

    def test_segments_checked_count(self):
        shots = [{"id": f"s{i}", "duration_sec": 5.0} for i in range(6)]
        pace = [
            {"label": "a", "start_ratio": 0.0, "end_ratio": 0.33, "cut_freq": "slow"},
            {"label": "b", "start_ratio": 0.33, "end_ratio": 0.66, "cut_freq": "medium"},
            {"label": "c", "start_ratio": 0.66, "end_ratio": 1.0, "cut_freq": "fast"},
        ]
        result = verify_pace_chart(shots, pace, total_duration=30.0)
        assert result["segments_checked"] == 3
