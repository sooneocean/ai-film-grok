"""Tests for act_structure ratio verification.

Verifies:
- ACT_RATIO_MISMATCH when actual proportions deviate from declared
- No mismatch when proportions are within tolerance
- Custom tolerance parameter
- Empty shots or act_structure → ok
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from rhythm import verify_act_structure


class TestActStructureVerification:
    """verify_act_structure checks actual proportions vs declared ratios."""

    def test_mismatch_detected(self):
        """Declared 0.20 setup but actual is 0.50 → mismatch."""
        shots = [
            {"id": "s1", "dramatic_function": "hook", "duration_sec": 5.0},
            {"id": "s2", "dramatic_function": "approach", "duration_sec": 5.0},
            {"id": "s3", "dramatic_function": "action", "duration_sec": 5.0},
            {"id": "s4", "dramatic_function": "afterglow", "duration_sec": 5.0},
        ]
        act = {"setup_ratio": 0.20, "confrontation_ratio": 0.50, "resolution_ratio": 0.30}
        result = verify_act_structure(shots, act, total_duration=20.0)
        # setup = 10/20 = 0.50 vs declared 0.20 → mismatch (Δ=0.30 > 0.10)
        assert "ACT_RATIO_MISMATCH" in result["codes"]

    def test_no_mismatch_when_matching(self):
        """Declared ratios match actual proportions."""
        shots = [
            {"id": "s1", "dramatic_function": "hook", "duration_sec": 4.0},
            {"id": "s2", "dramatic_function": "approach", "duration_sec": 4.0},
            {"id": "s3", "dramatic_function": "action", "duration_sec": 10.0},
            {"id": "s4", "dramatic_function": "sensory", "duration_sec": 5.0},
            {"id": "s5", "dramatic_function": "afterglow", "duration_sec": 5.0},
            {"id": "s6", "dramatic_function": "bridge", "duration_sec": 2.0},
        ]
        # total = 30s; setup=8s=0.27; confrontation=15s=0.50; resolution=7s=0.23
        act = {"setup_ratio": 0.27, "confrontation_ratio": 0.50, "resolution_ratio": 0.23}
        result = verify_act_structure(shots, act, total_duration=30.0)
        assert result["ok"] is True

    def test_custom_tolerance(self):
        """With large tolerance, small deviations pass."""
        shots = [
            {"id": "s1", "dramatic_function": "hook", "duration_sec": 5.0},
            {"id": "s2", "dramatic_function": "action", "duration_sec": 5.0},
            {"id": "s3", "dramatic_function": "afterglow", "duration_sec": 5.0},
        ]
        # setup=5/15=0.33, confrontation=5/15=0.33, resolution=5/15=0.33
        act = {"setup_ratio": 0.20, "confrontation_ratio": 0.50, "resolution_ratio": 0.30}
        # Max Δ is confrontation: 0.33 vs 0.50 = 0.17; tolerance=0.20 → no mismatch
        result = verify_act_structure(shots, act, total_duration=15.0, tolerance=0.20)
        assert result["ok"] is True

    def test_empty_shots_ok(self):
        result = verify_act_structure([], {"setup_ratio": 0.2})
        assert result["ok"] is True

    def test_empty_act_structure_ok(self):
        shots = [{"id": "s1", "dramatic_function": "hook", "duration_sec": 5.0}]
        result = verify_act_structure(shots, {})
        assert result["ok"] is True

    def test_actual_ratios_returned(self):
        shots = [
            {"id": "s1", "dramatic_function": "hook", "duration_sec": 3.0},
            {"id": "s2", "dramatic_function": "action", "duration_sec": 6.0},
            {"id": "s3", "dramatic_function": "afterglow", "duration_sec": 3.0},
        ]
        act = {"setup_ratio": 0.25, "confrontation_ratio": 0.50, "resolution_ratio": 0.25}
        result = verify_act_structure(shots, act, total_duration=12.0)
        ratios = result["actual_ratios"]
        assert abs(ratios["setup"] - 0.25) < 0.01
        assert abs(ratios["confrontation"] - 0.50) < 0.01
        assert abs(ratios["resolution"] - 0.25) < 0.01

    def test_bridge_maps_to_resolution(self):
        shots = [
            {"id": "s1", "dramatic_function": "hook", "duration_sec": 2.0},
            {"id": "s2", "dramatic_function": "action", "duration_sec": 6.0},
            {"id": "s3", "dramatic_function": "bridge", "duration_sec": 4.0},
        ]
        act = {"setup_ratio": 0.17, "confrontation_ratio": 0.50, "resolution_ratio": 0.33}
        result = verify_act_structure(shots, act, total_duration=12.0)
        # setup=2/12=0.167, confrontation=6/12=0.50, resolution=4/12=0.333
        ratios = result["actual_ratios"]
        assert abs(ratios["resolution"] - 0.333) < 0.01
