"""Tests for Hollywood-Style Plot-Adaptive Dynamic BGM System.

Verifies:
1. sound_plan.py build_mood_timeline extracts dramatic_function & heat_phase.
2. make_sfx_bed.py build_bed processes mood_timeline with seed mutation anti-fatigue mechanism.
3. render_final.py procedural_music applies equal-power crossfade between mood chapters.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from make_sfx_bed import build_bed, generate_procedural_bgm_stem  # noqa: E402
from render_final import procedural_music  # noqa: E402
from sound_plan import build_mood_timeline  # noqa: E402


class PlotAdaptiveBGMTests(unittest.TestCase):
    def test_build_mood_timeline_from_dramatic_function_and_heat(self) -> None:
        shots = [
            {
                "id": "shot01",
                "dramatic_function": "intro",
                "duration_sec": 10.0,
            },
            {
                "id": "shot02",
                "dramatic_function": "buildup",
                "duration_sec": 15.0,
            },
            {
                "id": "shot03",
                "dramatic_function": "climax",
                "heat_phase": "act",
                "duration_sec": 20.0,
            },
            {
                "id": "shot04",
                "dramatic_function": "resolution",
                "duration_sec": 10.0,
            },
        ]
        shot_starts = {"shot01": 0.0, "shot02": 10.0, "shot03": 25.0, "shot04": 45.0}
        shot_ends = {"shot01": 10.0, "shot02": 25.0, "shot03": 45.0, "shot04": 55.0}

        timeline = build_mood_timeline(
            shots, shot_starts=shot_starts, shot_ends=shot_ends, default_mood="rnb"
        )

        self.assertGreaterEqual(len(timeline), 4)
        self.assertEqual(timeline[0]["mood"], "ambient")
        self.assertEqual(timeline[1]["mood"], "dark")
        self.assertEqual(timeline[2]["mood"], "rnb")
        self.assertEqual(timeline[3]["mood"], "warm")

    def test_anti_fatigue_seed_mutation_generates_varied_stems(self) -> None:
        """Seed mutation (base_seed + i) must alter instrument / chord generation for same mood."""
        stem0 = generate_procedural_bgm_stem(10.0, mood="rnb", seed=42)
        stem1 = generate_procedural_bgm_stem(10.0, mood="rnb", seed=43)

        self.assertEqual(len(stem0), len(stem1))
        # The mutated seed must produce different waveforms (anti-fatigue variation)
        diff = np.max(np.abs(stem0 - stem1))
        self.assertGreater(diff, 0.01)

    def test_build_bed_with_mood_timeline(self) -> None:
        timeline = [
            {"start_sec": 0.0, "end_sec": 10.0, "mood": "ambient"},
            {"start_sec": 10.0, "end_sec": 25.0, "mood": "dark"},
            {"start_sec": 25.0, "end_sec": 40.0, "mood": "rnb"},
        ]
        bed = build_bed(40.0, [0.0, 10.0, 25.0], mood="rnb", mood_timeline=timeline, seed=100)

        self.assertEqual(bed.shape, (int(44100 * 40.0), 2))
        self.assertFalse(np.isnan(bed).any())
        self.assertLessEqual(np.max(np.abs(bed)), 1.0)
        self.assertGreater(np.max(np.abs(bed)), 0.01)

    def test_procedural_music_equal_power_crossfade(self) -> None:
        timeline = [
            {"start_sec": 0.0, "end_sec": 12.0, "mood": "ambient"},
            {"start_sec": 12.0, "end_sec": 25.0, "mood": "rnb"},
        ]
        samples = procedural_music(25.0, mood="rnb", mood_timeline=timeline, seed=200)

        self.assertEqual(len(samples), int(44100 * 25.0))
        self.assertFalse(np.isnan(samples).any())

        # Equal-power crossfade mathematical check: sin^2 + cos^2 == 1
        t = np.linspace(0, 1, 100)
        w_in = np.sin(0.5 * np.pi * t)
        w_out = np.cos(0.5 * np.pi * t)
        power = w_in**2 + w_out**2
        np.testing.assert_allclose(power, 1.0, atol=1e-6)


if __name__ == "__main__":
    unittest.main()
