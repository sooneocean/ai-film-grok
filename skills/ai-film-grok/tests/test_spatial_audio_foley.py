"""Unit tests for Plate 8: Spatial Audio & Room Impulse Response Foley Engineering System.

Verifies:
1. make_sfx_bed.py apply_spatial_pan equal-power panning and energy preservation.
2. make_sfx_bed.py apply_room_reverb room impulse response decay synthesis.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from make_sfx_bed import RIR_ROOM_PRESETS, apply_room_reverb, apply_spatial_pan  # noqa: E402


class SpatialAudioFoleyTests(unittest.TestCase):
    def test_apply_spatial_pan_center_equal_power(self) -> None:
        samples = np.ones(1000)
        panned = apply_spatial_pan(samples, pan=0.0)

        # At pan=0, angle=pi/4, left = cos(pi/4) = sqrt(2)/2, right = sin(pi/4) = sqrt(2)/2
        left_power = np.mean(panned[:, 0] ** 2)
        right_power = np.mean(panned[:, 1] ** 2)

        self.assertAlmostEqual(left_power, 0.5, places=3)
        self.assertAlmostEqual(right_power, 0.5, places=3)
        self.assertAlmostEqual(left_power + right_power, 1.0, places=3)

    def test_apply_spatial_pan_hard_left(self) -> None:
        samples = np.ones(1000)
        panned = apply_spatial_pan(samples, pan=-1.0)

        self.assertAlmostEqual(np.max(np.abs(panned[:, 0])), 1.0, places=3)
        self.assertAlmostEqual(np.max(np.abs(panned[:, 1])), 0.0, places=3)

    def test_apply_room_reverb(self) -> None:
        self.assertIn("bedroom", RIR_ROOM_PRESETS)
        self.assertIn("bathroom", RIR_ROOM_PRESETS)
        self.assertIn("spacious_hall", RIR_ROOM_PRESETS)

        samples = np.zeros(44100)
        samples[0] = 1.0  # Impulse

        reverbed = apply_room_reverb(samples, room_type="bedroom")
        self.assertEqual(len(reverbed), len(samples))
        self.assertTrue(np.any(reverbed[100:500] != 0.0))


if __name__ == "__main__":
    unittest.main()
