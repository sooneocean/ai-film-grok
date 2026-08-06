#!/usr/bin/env python3
"""Contract-level regression for references/hard-defaults.md.

These tests assert that the *machine-readable* hard rules declared in
hard-defaults.md (numeric floors, enum members, strict-flag defaults) have not
been silently weakened. They complement the behavioral tests in
test_heat_arc_multi / test_edit_policy which exercise the *behavior*; here we
lock the *contract* so a rule change must touch both the doc and the code.

If you intentionally change a floor/enum, update hard-defaults.md AND this test
in the same commit.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from director_review import SCORECARD_DIMENSIONS  # noqa: E402
from edit_policy import (  # noqa: E402
    DEFAULT_SEX_DURATION_FLOOR,
    HOT_SEX_DURATION_FLOOR,
    lint_heat_arc,
)
from i2v_motion_gate import (  # noqa: E402
    MEAN_MEAT_FLOOR,
    MEAN_MEAT_TARGET,
    MEAN_NORMAL_FLOOR,
)
from media_qa import (  # noqa: E402
    STILL_ASPECT_9_16_MAX,
    STILL_ASPECT_9_16_MIN,
    STILL_MIN_HEIGHT_9_16,
    STILL_MIN_WIDTH_9_16,
)
from state_index_gate import UNDRESS_STATES, WARDROBE_RANK  # noqa: E402


def _shot(sid: str, phase: str, dur: float = 6.0) -> dict[str, object]:
    return {"id": sid, "heat_phase": phase, "duration_sec": dur}


class HardDefaultsContractTests(unittest.TestCase):
    """Lock the hard-defaults.md contract values to the code."""

    # --- §叙事与规划: 性爱片段时长硬底 (adult max IRON 2026-07-24 · 50%) ---
    def test_sex_duration_floor_is_50_percent(self) -> None:
        """hard-defaults.md IRON: DEFAULT_SEX_DURATION_FLOOR == 0.50."""
        self.assertEqual(DEFAULT_SEX_DURATION_FLOOR, 0.50)

    def test_hot_floor_is_15_percent(self) -> None:
        """hard-defaults.md: hot (non-max) floor is lower — 0.15."""
        self.assertEqual(HOT_SEX_DURATION_FLOOR, 0.15)

    def test_max_sex_duration_below_floor_warns(self) -> None:
        """heat_scale=max: act+climax duration ratio < 0.50 → HEAT_SEX_DURATION_LOW."""
        shots = [_shot(f"s{i:02d}", "setup") for i in range(7)]
        shots += [_shot(f"a{i:02d}", "act") for i in range(2)]  # 2/10 = 0.20 < 0.50
        rep = lint_heat_arc(shots, heat_scale="max", advise=True)
        self.assertIn("HEAT_SEX_DURATION_LOW", rep.get("codes", []))

    def test_max_sex_duration_at_floor_passes(self) -> None:
        """heat_scale=max: act+climax ratio == 0.50 → no HEAT_SEX_DURATION_LOW."""
        shots = [_shot(f"s{i:02d}", "setup") for i in range(5)]
        shots += [_shot(f"a{i:02d}", "act") for i in range(5)]  # 5/10 = 0.50
        rep = lint_heat_arc(shots, heat_scale="max", advise=True)
        self.assertNotIn("HEAT_SEX_DURATION_LOW", rep.get("codes", []))

    def test_sex_floor_reported(self) -> None:
        """heat report exposes sex_duration_floor == 0.50 for max scale."""
        shots = [_shot("s00", "setup"), _shot("a00", "act")]
        rep = lint_heat_arc(shots, heat_scale="max", advise=True)
        self.assertAlmostEqual(rep["sex_duration_floor"], 0.50, places=2)

    # --- §叙事与规划: 卸装延续·不回穿 ---
    def test_wardrobe_rank_monotonic_no_redress(self) -> None:
        """hard-defaults.md: 'rank 单调不降；回穿自动 clamp'.

        WARDROBE_RANK must order full < partial < undressed < bare so a drop
        (e.g. undressed→full) is detectable as re-dress.
        """
        self.assertLess(WARDROBE_RANK["full"], WARDROBE_RANK["partial"])
        self.assertLess(WARDROBE_RANK["partial"], WARDROBE_RANK["undressed"])
        self.assertLess(WARDROBE_RANK["undressed"], WARDROBE_RANK["bare"])

    def test_undress_states_excludes_full(self) -> None:
        """hard-defaults.md: act/climax wardrobe = partial|undressed|bare."""
        self.assertEqual(UNDRESS_STATES, frozenset({"partial", "undressed", "bare"}))
        self.assertNotIn("full", UNDRESS_STATES)
        self.assertNotIn("armored", UNDRESS_STATES)

    # --- §视觉: 高动态常态 (2026-07-27) ---
    def test_high_motion_normal_floor_18(self) -> None:
        """hard-defaults.md: 平常 mean≥18."""
        self.assertEqual(MEAN_NORMAL_FLOOR, 18.0)

    def test_high_motion_meat_floor_20(self) -> None:
        """hard-defaults.md: 肉戏 act/climax mean≥20（目标≥24）."""
        self.assertEqual(MEAN_MEAT_FLOOR, 20.0)
        self.assertEqual(MEAN_MEAT_TARGET, 24.0)

    # --- §后期: 导演复审十六维 ---
    def test_review_scorecard_has_sixteen_dimensions(self) -> None:
        """Cinema quality contract: all sixteen dimensions must pass."""
        expected = (
            "identity",
            "style",
            "motion",
            "escalation",
            "audio",
            "subs",
            "dead_air",
            "rhythm",
            "emotion",
            "theme",
            "performance",
            "cinematic_coherence",
            "coverage_sufficiency",
            "performance_truth",
            "editorial_rhythm",
            "whole_film_integrity",
        )
        self.assertEqual(SCORECARD_DIMENSIONS, expected)
        self.assertEqual(len(SCORECARD_DIMENSIONS), 16)

    # --- §视觉: 静帧几何·禁压缩 ---
    def test_keyframe_min_dimensions(self) -> None:
        """hard-defaults.md: FRW native keyframes stay at 704×1280."""
        self.assertEqual(STILL_MIN_WIDTH_9_16, 704)
        self.assertEqual(STILL_MIN_HEIGHT_9_16, 1280)

    def test_keyframe_aspect_allows_provider_native_vertical_geometry(self) -> None:
        """704×1280 is the accepted provider-native near-9:16 geometry."""
        ratio = STILL_MIN_WIDTH_9_16 / STILL_MIN_HEIGHT_9_16
        self.assertAlmostEqual(ratio, 704 / 1280, places=2)
        self.assertGreaterEqual(ratio, STILL_ASPECT_9_16_MIN)
        self.assertLessEqual(ratio, STILL_ASPECT_9_16_MAX)

    # --- §量产十条: pilot 用户批准才 bulk ---
    def test_pilot_gate_not_skipped_by_default(self) -> None:
        """hard-defaults.md §2: 'pilot 用户批准 → 才 bulk'.

        skip_pilot_gate must default False (gate ON) unless explicitly set.
        """
        from config_loader import ConfigSchema

        # ConfigSchema is a dataclass with skip_pilot_gate defaulting False.
        cfg = ConfigSchema()
        self.assertFalse(
            cfg.skip_pilot_gate,
            "skip_pilot_gate must default False — pilot approval is a hard gate",
        )


if __name__ == "__main__":
    unittest.main()
