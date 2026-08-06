"""Auto last→first promote rules (generation continuity · 2026-07-21)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from continuity_chain import (  # noqa: E402
    next_shot_after,
    should_auto_promote_next,
)


class FramePromoteRules(unittest.TestCase):
    def test_next_shot_after(self) -> None:
        spec = {
            "scenes": [
                {
                    "shots": [
                        {"id": "shot01"},
                        {"id": "shot02"},
                        {"id": "shot03"},
                    ]
                }
            ]
        }
        n = next_shot_after(spec, "shot01")
        assert n is not None
        self.assertEqual(n["id"], "shot02")
        self.assertIsNone(next_shot_after(spec, "shot03"))

    def test_promote_on_undress(self) -> None:
        prev = {
            "id": "shot03",
            "wardrobe_state": "partial",
            "dsl": {"chain_mode": "continue", "wardrobe_state": "partial"},
        }
        nxt = {"id": "shot04", "wardrobe_state": "undressed", "dsl": {}}
        do, why = should_auto_promote_next(prev, nxt, heat_scale="max")
        self.assertTrue(do, why)

    def test_no_promote_on_cut(self) -> None:
        prev = {
            "id": "shot03",
            "wardrobe_state": "bare",
            "dsl": {"chain_mode": "cut"},
        }
        nxt = {"id": "shot04", "dsl": {"chain_mode": "cut"}}
        do, why = should_auto_promote_next(prev, nxt, heat_scale="max")
        self.assertFalse(do, why)

    def test_max_default_serial(self) -> None:
        prev = {"id": "shot01", "wardrobe_state": "full", "dsl": {}}
        nxt = {"id": "shot02", "wardrobe_state": "full", "dsl": {}}
        do, why = should_auto_promote_next(prev, nxt, heat_scale="max")
        self.assertTrue(do, why)

    def test_soft_no_undress_no_max(self) -> None:
        prev = {"id": "shot01", "wardrobe_state": "full", "dsl": {}}
        nxt = {"id": "shot02", "wardrobe_state": "full", "dsl": {}}
        do, why = should_auto_promote_next(prev, nxt, heat_scale="soft")
        self.assertFalse(do, why)


if __name__ == "__main__":
    unittest.main()
