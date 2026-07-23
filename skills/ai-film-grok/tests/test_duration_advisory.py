#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from compose_render import (  # noqa: E402
    HF_HARD_CEILING_SEC,
    HF_STRONG_MAX_SEC,
    duration_advisory,
)


class DurationAdvisoryTests(unittest.TestCase):
    def test_no_advisory_under_90s(self) -> None:
        """≤90s (HF sweet spot) → no advisory."""
        r = duration_advisory(60.0)
        self.assertFalse(r["advisory"])
        self.assertIsNone(r["action"])
        self.assertEqual(r["segment_count"], 1)

    def test_advisory_between_90_and_180(self) -> None:
        """>90s but ≤180s → segment into ≤90s chunks + concat advisory."""
        r = duration_advisory(120.0)
        self.assertTrue(r["advisory"])
        self.assertIn("segment", r["action"])
        self.assertGreaterEqual(r["segment_count"], 2)

    def test_advisory_over_ceiling(self) -> None:
        """>180s HF ceiling → route to /general-video style."""
        r = duration_advisory(300.0)
        self.assertTrue(r["advisory"])
        self.assertIn("ceiling", r["action"])
        self.assertGreaterEqual(r["segment_count"], 3)

    def test_zero_or_none_duration(self) -> None:
        self.assertFalse(duration_advisory(None)["advisory"])
        self.assertFalse(duration_advisory(0.0)["advisory"])
        self.assertFalse(duration_advisory(-5.0)["advisory"])

    def test_boundaries(self) -> None:
        self.assertFalse(duration_advisory(HF_STRONG_MAX_SEC)["advisory"])
        self.assertTrue(duration_advisory(HF_STRONG_MAX_SEC + 0.01)["advisory"])
        self.assertTrue(duration_advisory(HF_HARD_CEILING_SEC)["advisory"])
        self.assertTrue(duration_advisory(HF_HARD_CEILING_SEC + 0.01)["advisory"])


if __name__ == "__main__":
    unittest.main()
