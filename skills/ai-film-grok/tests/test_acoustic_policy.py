"""Tests for acoustic_policy.py — spatial audio and reverb mapping.

Previously had ZERO test coverage despite feeding sound_plan DSP parameters.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from acoustic_policy import resolve_acoustic_space, resolve_spatial_pan  # noqa: E402


class TestResolveAcousticSpace(unittest.TestCase):
    """resolve_acoustic_space maps location tags to reverb/EQ params."""

    def test_bathroom_reverb(self):
        r = resolve_acoustic_space(["bathroom"])
        self.assertGreater(r["reverb_time"], 2.0)
        self.assertGreater(r["wet_level"], 0.3)

    def test_hallway_reverb(self):
        r = resolve_acoustic_space(["hallway"])
        self.assertGreater(r["reverb_time"], 2.0)

    def test_outdoor_low_reverb(self):
        r = resolve_acoustic_space(["outdoor"])
        self.assertLess(r["reverb_time"], 1.0)
        self.assertLess(r["wet_level"], 0.2)

    def test_street(self):
        r = resolve_acoustic_space(["street"])
        self.assertLess(r["reverb_time"], 1.0)

    def test_bedroom_intimate(self):
        r = resolve_acoustic_space(["bedroom", "intimate"])
        self.assertLess(r["reverb_time"], 1.0)
        self.assertLess(r["wet_level"], 0.2)

    def test_default_indoor(self):
        r = resolve_acoustic_space(["classroom"])
        self.assertAlmostEqual(r["reverb_time"], 1.2)

    def test_empty_tags_uses_default(self):
        r = resolve_acoustic_space([])
        self.assertAlmostEqual(r["reverb_time"], 1.2)

    def test_none_tags_safe(self):
        r = resolve_acoustic_space(None)  # type: ignore[arg-type]
        self.assertIn("reverb_time", r)

    def test_case_insensitive(self):
        r1 = resolve_acoustic_space(["BATHROOM"])
        r2 = resolve_acoustic_space(["bathroom"])
        self.assertEqual(r1, r2)


class TestResolveSpatialPan(unittest.TestCase):
    """resolve_spatial_pan maps framing to stereo pan [-1.0, 1.0]."""

    def test_center_default(self):
        self.assertEqual(resolve_spatial_pan(""), 0.0)
        self.assertEqual(resolve_spatial_pan("closeup"), 0.0)

    def test_left_pan(self):
        pan = resolve_spatial_pan("left profile")
        self.assertLess(pan, 0.0)

    def test_right_pan(self):
        pan = resolve_spatial_pan("right profile")
        self.assertGreater(pan, 0.0)

    def test_extreme_left(self):
        pan = resolve_spatial_pan("extreme left")
        self.assertLessEqual(pan, -0.8)

    def test_extreme_right(self):
        pan = resolve_spatial_pan("far right")
        self.assertGreaterEqual(pan, 0.8)

    def test_case_insensitive(self):
        self.assertEqual(resolve_spatial_pan("LEFT"), resolve_spatial_pan("left"))

    def test_empty_framing(self):
        self.assertEqual(resolve_spatial_pan(""), 0.0)

    def test_none_framing(self):
        self.assertEqual(resolve_spatial_pan(None), 0.0)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
