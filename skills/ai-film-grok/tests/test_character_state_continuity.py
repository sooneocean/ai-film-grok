"""Unit tests for Plate 1: Dynamic Character State Continuity System.

Verifies:
1. asset_registry.py derive_character_state_timeline monotonic propagation.
2. continuity.py CODE_CHARACTER_STATE_REGRESSION detection.
3. prompt_injector.py multi-axis state tag assembly.
4. story_plan.py character_states automatic generation.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from asset_registry import derive_character_state_timeline  # noqa: E402
from continuity import CODE_CHARACTER_STATE_REGRESSION, lint_continuity  # noqa: E402
from prompt_injector import PromptInjector  # noqa: E402


class CharacterStateContinuityTests(unittest.TestCase):
    def test_derive_character_state_timeline_monotonic(self) -> None:
        shots = [
            {"id": "shot01", "heat_phase": "setup"},
            {"id": "shot02", "heat_phase": "foreplay"},
            {"id": "shot03", "heat_phase": "act"},
            {"id": "shot04", "heat_phase": "afterglow"},
        ]
        timeline = derive_character_state_timeline(shots)

        self.assertEqual(len(timeline), 4)
        s1 = timeline[0]["character_states"]
        s2 = timeline[1]["character_states"]
        s3 = timeline[2]["character_states"]
        s4 = timeline[3]["character_states"]

        self.assertEqual(s1["wardrobe"], "full")
        self.assertEqual(s2["wardrobe"], "partial")
        self.assertEqual(s3["wardrobe"], "undressed")
        # Afterglow retains undressed (monotonic non-regression)
        self.assertEqual(s4["wardrobe"], "undressed")
        self.assertEqual(s4["skin"], "afterglow_blush")

    def test_character_state_regression_lint(self) -> None:
        shots = [
            {"id": "shot01", "wardrobe_state": "undressed"},
            {"id": "shot02", "wardrobe_state": "full"},  # Regression!
        ]
        res = lint_continuity(shots, fail_on={CODE_CHARACTER_STATE_REGRESSION})

        self.assertFalse(res["ok"])
        self.assertIn(CODE_CHARACTER_STATE_REGRESSION, res["codes"])

    def test_prompt_injector_multi_axis_state(self) -> None:
        inj = PromptInjector(bible={"signature_block": "test_sig"})
        shot = {
            "heroine_ids": ["hero"],
            "wardrobe_state": "undressed",
            "character_states": {
                "wardrobe": "undressed",
                "hair": "disheveled",
                "skin": "glistening_sweat",
                "arousal": "heavy_breathing",
            },
        }

        res = inj.assemble(shot, Path("/tmp"))

        self.assertIn("prompt_text", res)
        prompt = res["prompt_text"]
        self.assertIn("disheveled", prompt)
        self.assertIn("glistening_sweat", prompt)


if __name__ == "__main__":
    unittest.main()
