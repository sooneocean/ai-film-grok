from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from h3_fill_idle import classify_primary_h3_shot  # noqa: E402

pytestmark = pytest.mark.hotpath


def _h3_take(name: str, *, mean: float | None = None) -> dict:
    return {"lane": "h3", "path": f"takes/s01/h3_{name}.mp4", "mean": mean}


class ClassifyPrimaryH3ShotTests(unittest.TestCase):
    # --- priority tiers (P0a / P0b / P0c) ----------------------------------

    def test_p0a_restricted_default(self):
        pri, lane, status, reasons = classify_primary_h3_shot(
            shot={}, intent={}, takes=[], wants_continue=False,
            on_cam=False, close=False, has_h3=False, below=False,
            has_last=False, best=None, floor=None,
        )
        self.assertEqual((pri, lane, status, reasons),
                         ("P0a", "primary_h3", "pending", ["restricted_primary", "needs_h3_primary"]))

    def test_p0c_continue_endframe(self):
        pri, lane, status, reasons = classify_primary_h3_shot(
            shot={}, intent={}, takes=[], wants_continue=True,
            on_cam=False, close=False, has_h3=False, below=False,
            has_last=False, best=None, floor=None,
        )
        self.assertEqual((pri, lane, status, reasons),
                         ("P0c", "primary_h3", "pending", ["continue_endframe", "needs_h3_primary"]))

    def test_p0b_dialogue_close_restricted(self):
        pri, lane, status, reasons = classify_primary_h3_shot(
            shot={}, intent={}, takes=[], wants_continue=False,
            on_cam=True, close=True, has_h3=False, below=False,
            has_last=False, best=None, floor=None,
        )
        self.assertEqual((pri, lane, status, reasons),
                         ("P0b", "primary_h3", "pending", ["dialogue_close_restricted", "needs_h3_primary"]))

    # --- H3 take exists, above floor ---------------------------------------

    def test_h3_take_ok(self):
        pri, lane, status, reasons = classify_primary_h3_shot(
            shot={}, intent={}, takes=[_h3_take("a", mean=50)],
            wants_continue=False, on_cam=False, close=False,
            has_h3=True, below=False, has_last=False, best=50, floor=20,
        )
        self.assertEqual((pri, lane, status, reasons),
                         ("P0a", "primary_h3", "done", ["restricted_primary", "h3_take_ok"]))

    # --- H3 take below floor (P1 retry + cap exhaustion) -------------------

    def test_h3_below_floor_p1_retry(self):
        takes = [_h3_take(str(i), mean=5) for i in range(3)]
        pri, lane, status, reasons = classify_primary_h3_shot(
            shot={}, intent={}, takes=takes, wants_continue=False,
            on_cam=False, close=False, has_h3=True, below=True,
            has_last=False, best=5, floor=20,
        )
        self.assertEqual((pri, lane, status, reasons),
                         ("P1", "primary_h3", "retry", ["restricted_primary", "h3_below_floor"]))

    def test_h3_floor_retry_exhausted(self):
        # default cap is 5 -> 5 takes => exhausted, dropped from pending.
        takes = [_h3_take(str(i), mean=5) for i in range(5)]
        pri, lane, status, reasons = classify_primary_h3_shot(
            shot={}, intent={}, takes=takes, wants_continue=False,
            on_cam=False, close=False, has_h3=True, below=True,
            has_last=False, best=5, floor=20,
        )
        self.assertEqual((pri, lane, status), ("done", "primary_h3", "done"))
        self.assertIn("h3_floor_retry_exhausted", reasons)
        self.assertIn("h3_takes=5>=5", reasons)

    # --- dual I2V + R2V ----------------------------------------------------

    def test_dual_complete(self):
        takes = [_h3_take("i2v_a", mean=40), _h3_take("r2v_a", mean=40)]
        pri, lane, status, reasons = classify_primary_h3_shot(
            shot={"h3_prefer": "dual"}, intent={}, takes=takes,
            wants_continue=False, on_cam=False, close=False,
            has_h3=True, below=False, has_last=False, best=40, floor=20,
        )
        self.assertEqual((pri, lane, status, reasons),
                         ("P0a", "primary_h3", "done", ["restricted_primary", "h3_dual_complete"]))

    def test_dual_need_i2v_with_last(self):
        takes = [_h3_take("r2v_a", mean=40)]
        pri, lane, status, reasons = classify_primary_h3_shot(
            shot={"h3_prefer": "dual"}, intent={}, takes=takes,
            wants_continue=False, on_cam=False, close=False,
            has_h3=True, below=False, has_last=True, best=40, floor=20,
        )
        self.assertEqual((pri, lane, status, reasons),
                         ("P0a", "primary_h3", "pending",
                          ["restricted_primary", "dual_need_i2v", "dual_prefer_flf"]))

    # --- dual I2V present, no R2V: γ3 strong-skip vs need ------------------

    def test_skip_r2v_i2v_strong_enough(self):
        # dual via climax (explicit=False); i2v mean >= floor+4 -> skip blind R2V.
        takes = [_h3_take("i2v_a", mean=30)]
        # dual driven by climax heat_phase (not dialogue-close), so priority stays P0a.
        pri, lane, status, reasons = classify_primary_h3_shot(
            shot={}, intent={"heat_phase": "climax"}, takes=takes,
            wants_continue=False, on_cam=False, close=False,
            has_h3=True, below=False, has_last=False, best=30, floor=20,
        )
        self.assertEqual((pri, lane, status, reasons),
                         ("P0a", "primary_h3", "done", ["restricted_primary", "skip_r2v_i2v_strong_enough"]))

    def test_dual_need_r2v_when_i2v_weak(self):
        # dual via climax; i2v mean below floor+4 -> still need R2V energy leg.
        takes = [_h3_take("i2v_a", mean=10)]
        # dual driven by climax heat_phase (not dialogue-close), so priority stays P0a.
        pri, lane, status, reasons = classify_primary_h3_shot(
            shot={}, intent={"heat_phase": "climax"}, takes=takes,
            wants_continue=False, on_cam=False, close=False,
            has_h3=True, below=False, has_last=False, best=10, floor=20,
        )
        self.assertEqual((pri, lane, status, reasons),
                         ("P0a", "primary_h3", "pending", ["restricted_primary", "dual_need_r2v"]))

    def test_explicit_dual_forces_r2v_even_when_strong(self):
        # explicit dual flag overrides the γ3 strong-skip.
        takes = [_h3_take("i2v_a", mean=30)]
        pri, lane, status, reasons = classify_primary_h3_shot(
            shot={"h3_prefer": "dual"}, intent={}, takes=takes,
            wants_continue=False, on_cam=False, close=False,
            has_h3=True, below=False, has_last=False, best=30, floor=20,
        )
        self.assertEqual((pri, lane, status, reasons),
                         ("P0a", "primary_h3", "pending", ["restricted_primary", "dual_need_r2v"]))


if __name__ == "__main__":
    unittest.main()
