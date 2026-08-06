"""Unit tests for Plate 5: Gaze Axis & Eye-Contact Tracking System.

Verifies:
1. continuity.py CODE_GAZE_MISALIGNMENT detection.
2. prompt_injector.py gaze_target formatting in prompt text.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from continuity import CODE_GAZE_MISALIGNMENT, lint_continuity  # noqa: E402
from prompt_injector import PromptInjector  # noqa: E402


class GazeTrackingTests(unittest.TestCase):
    def test_gaze_misalignment_lint(self) -> None:
        shots = [
            {"id": "shot01", "gaze_target": "intense_eye_contact"},
            {"id": "shot02", "gaze_target": "gaze_away_abrupt"},
        ]
        res = lint_continuity(shots)

        self.assertIn(CODE_GAZE_MISALIGNMENT, res["codes"])

    def test_prompt_injector_gaze_target(self) -> None:
        inj = PromptInjector(bible={"signature_block": "test_sig"})
        shot = {
            "heroine_ids": ["hero"],
            "wardrobe_state": "undressed",
            "gaze_target": "intense_eye_contact",
        }

        res = inj.assemble(shot, Path("/tmp"))

        self.assertIn("prompt_text", res)
        prompt = res["prompt_text"]
        self.assertIn("intense eye contact", prompt)


if __name__ == "__main__":
    unittest.main()
