"""Unit tests for Plate 6: Cinematic Color-Grading & Lighting Timeline System.

Verifies:
1. visual_bible.py derive_lighting_timeline mapping heat phases to presets.
2. FFmpeg color filter strings for setup, foreplay, climax, afterglow.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from visual_bible import LIGHTING_COLOR_PALETTES, derive_lighting_timeline  # noqa: E402


class CinematicColorGradingTests(unittest.TestCase):
    def test_lighting_palettes_exist(self) -> None:
        self.assertIn("setup", LIGHTING_COLOR_PALETTES)
        self.assertIn("foreplay", LIGHTING_COLOR_PALETTES)
        self.assertIn("climax", LIGHTING_COLOR_PALETTES)
        self.assertIn("afterglow", LIGHTING_COLOR_PALETTES)

    def test_derive_lighting_timeline(self) -> None:
        shots = [
            {"id": "s1", "heat_phase": "setup"},
            {"id": "s2", "heat_phase": "foreplay"},
            {"id": "s3", "heat_phase": "climax"},
            {"id": "s4", "heat_phase": "afterglow"},
        ]
        timeline = derive_lighting_timeline(shots)

        self.assertEqual(len(timeline), 4)

        t1 = timeline[0]
        t2 = timeline[1]
        t3 = timeline[2]
        t4 = timeline[3]

        self.assertEqual(t1["lighting_theme"], "subdued_ambient")
        self.assertIn("colorbalance", t2["ffmpeg_filter"])
        self.assertIn("eq=contrast=1.2", t3["ffmpeg_filter"])
        self.assertEqual(t4["lighting_theme"], "warm_golden_hour")


if __name__ == "__main__":
    unittest.main()
