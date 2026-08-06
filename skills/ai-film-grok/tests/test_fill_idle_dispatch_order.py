from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from h3_fill_idle import fill_idle_sort_key  # noqa: E402

pytestmark = pytest.mark.hotpath


def _row(shot_id, priority, *, rank=None, dual_sticky=False, best_mean=None, h3_takes=0):
    return {
        "shot_id": shot_id,
        "priority": priority,
        "priority_rank": rank if rank is not None else {"P0": 10, "P1": 40, "P2": 50}.get(priority, 99),
        "dual_sticky": dual_sticky,
        "best_mean": best_mean,
        "takes": [{"lane": "h3"} for _ in range(h3_takes)],
    }


def _order(rows):
    return [r["shot_id"] for r in sorted(rows, key=fill_idle_sort_key)]


class DispatchOrderTests(unittest.TestCase):
    def test_priority_rank_order(self):
        rows = [
            _row("s09", "P2", best_mean=5),
            _row("s01", "P0", best_mean=5),
            _row("s05", "P1", best_mean=5),
        ]
        self.assertEqual(_order(rows), ["s01", "s05", "s09"])

    def test_dual_sticky_first_within_rank(self):
        rows = [
            _row("s02", "P0", dual_sticky=False),
            _row("s01", "P0", dual_sticky=True),
        ]
        self.assertEqual(_order(rows), ["s01", "s02"])

    def test_p2_lowest_mean_first(self):
        rows = [
            _row("s_hi", "P2", best_mean=8.0),
            _row("s_lo", "P2", best_mean=3.0),
        ]
        self.assertEqual(_order(rows), ["s_lo", "s_hi"])

    def test_p2_missing_mean_sorts_last(self):
        rows = [
            _row("s_none", "P2", best_mean=None),
            _row("s_lo", "P2", best_mean=2.0),
        ]
        self.assertEqual(_order(rows), ["s_lo", "s_none"])

    def test_p1_fewest_h3_takes_first(self):
        rows = [
            _row("s_many", "P1", best_mean=5.0, h3_takes=3),
            _row("s_few", "P1", best_mean=5.0, h3_takes=1),
        ]
        self.assertEqual(_order(rows), ["s_few", "s_many"])

    def test_p1_take_tie_breaks_on_mean(self):
        rows = [
            _row("s_hi", "P1", best_mean=9.0, h3_takes=1),
            _row("s_lo", "P1", best_mean=4.0, h3_takes=1),
        ]
        self.assertEqual(_order(rows), ["s_lo", "s_hi"])

    def test_shot_id_tiebreak(self):
        rows = [
            _row("s_b", "P0", best_mean=None),
            _row("s_a", "P0", best_mean=None),
        ]
        self.assertEqual(_order(rows), ["s_a", "s_b"])

    def test_full_policy_stability(self):
        rows = [
            _row("s_p2_lo", "P2", best_mean=2.0),
            _row("s_p2_hi", "P2", best_mean=7.0),
            _row("s_p1", "P1", best_mean=5.0, h3_takes=2),
            _row("s_p0", "P0", best_mean=5.0),
            _row("s_p0_sticky", "P0", best_mean=5.0, dual_sticky=True),
        ]
        self.assertEqual(
            _order(rows),
            ["s_p0_sticky", "s_p0", "s_p1", "s_p2_lo", "s_p2_hi"],
        )


if __name__ == "__main__":
    unittest.main()
