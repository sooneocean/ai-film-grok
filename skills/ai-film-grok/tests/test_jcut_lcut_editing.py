"""Unit tests for Plate 11: Cinematic J-Cut/L-Cut Micro-Editing Engine.

Verifies:
1. edit_policy.py derive_micro_edit_cut J-Cut derivation when entering climax.
2. edit_policy.py derive_micro_edit_cut L-Cut derivation when exiting climax.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from edit_policy import derive_micro_edit_cut  # noqa: E402


class JCutLCutEditingTests(unittest.TestCase):
    def test_derive_jcut_entering_climax(self) -> None:
        prev = {"id": "s1", "heat_phase": "setup"}
        cur = {"id": "s2", "heat_phase": "climax"}

        res = derive_micro_edit_cut(prev, cur)
        self.assertEqual(res["mode"], "j_cut")
        self.assertGreater(res["offset_sec"], 0.0)

    def test_derive_lcut_exiting_climax(self) -> None:
        prev = {"id": "s1", "heat_phase": "climax"}
        cur = {"id": "s2", "heat_phase": "afterglow"}

        res = derive_micro_edit_cut(prev, cur)
        self.assertEqual(res["mode"], "l_cut")
        self.assertGreater(res["offset_sec"], 0.0)

    def test_derive_standard_cut(self) -> None:
        prev = {"id": "s1", "heat_phase": "setup"}
        cur = {"id": "s2", "heat_phase": "foreplay"}

        res = derive_micro_edit_cut(prev, cur)
        self.assertEqual(res["mode"], "standard")
        self.assertEqual(res["offset_sec"], 0.0)


if __name__ == "__main__":
    unittest.main()
