from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from h3_fill_idle import decide_p2_challenge  # noqa: E402

pytestmark = pytest.mark.hotpath


class DecideP2ChallengeTests(unittest.TestCase):
    # --- H3 take already exists --------------------------------------------

    def test_h3_ok_no_rechallenge(self):
        pri, lane, status, reasons = decide_p2_challenge(
            has_h3=True, below=False, has_grok=False, best=50.0, floor=20.0
        )
        self.assertEqual((pri, lane, status, reasons), ("done", "challenge_grok", "done", ["already_challenged_ok"]))

    def test_h3_below_floor_p1_retry(self):
        pri, lane, status, reasons = decide_p2_challenge(
            has_h3=True, below=True, has_grok=False, best=5.0, floor=20.0
        )
        self.assertEqual((pri, lane, status, reasons), ("P1", "challenge_weak", "retry", ["challenge_below_floor"]))

    # --- no H3 take yet: γ3 low-ROI-skip ----------------------------------

    def test_baseline_strong_skip_p2(self):
        # best >= floor + 6.0 -> skip low-ROI P2 burn.
        pri, lane, status, reasons = decide_p2_challenge(
            has_h3=False, below=False, has_grok=True, best=40.0, floor=30.0
        )
        self.assertEqual((pri, lane, status, reasons), ("done", "challenge_grok", "done", ["skip_p2_baseline_strong"]))

    def test_baseline_strong_boundary_exact(self):
        # boundary best == floor + 6.0 -> still skipped (>=).
        pri, lane, status, reasons = decide_p2_challenge(
            has_h3=False, below=False, has_grok=False, best=36.0, floor=30.0
        )
        self.assertEqual((pri, lane, status, reasons), ("done", "challenge_grok", "done", ["skip_p2_baseline_strong"]))

    def test_baseline_just_below_threshold_enqueues_p2(self):
        # best == floor + 5.9 -> not strong enough -> enqueue P2.
        pri, lane, status, reasons = decide_p2_challenge(
            has_h3=False, below=False, has_grok=False, best=35.9, floor=30.0
        )
        self.assertEqual((pri, lane, status, reasons), ("P2", "challenge_grok", "pending", ["fill_idle_challenge"]))

    def test_weak_baseline_with_grok_marks_has_baseline(self):
        pri, lane, status, reasons = decide_p2_challenge(
            has_h3=False, below=False, has_grok=True, best=10.0, floor=20.0
        )
        self.assertEqual((pri, lane, status, reasons), ("P2", "challenge_grok", "pending", ["fill_idle_challenge", "has_baseline_take"]))

    def test_weak_baseline_no_grok_no_marker(self):
        pri, lane, status, reasons = decide_p2_challenge(
            has_h3=False, below=False, has_grok=False, best=10.0, floor=20.0
        )
        self.assertEqual((pri, lane, status, reasons), ("P2", "challenge_grok", "pending", ["fill_idle_challenge"]))

    # --- missing data guards ----------------------------------------------

    def test_missing_best_mean_enqueues_p2(self):
        # γ3 guard needs both floor and best; missing best -> no skip.
        pri, lane, status, reasons = decide_p2_challenge(
            has_h3=False, below=False, has_grok=False, best=None, floor=30.0
        )
        self.assertEqual((pri, lane, status, reasons), ("P2", "challenge_grok", "pending", ["fill_idle_challenge"]))

    def test_missing_floor_enqueues_p2(self):
        pri, lane, status, reasons = decide_p2_challenge(
            has_h3=False, below=False, has_grok=False, best=99.0, floor=None
        )
        self.assertEqual((pri, lane, status, reasons), ("P2", "challenge_grok", "pending", ["fill_idle_challenge"]))


if __name__ == "__main__":
    unittest.main()
