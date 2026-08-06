from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from rhythm import lint_rhythm  # noqa: E402


class RhythmTests(unittest.TestCase):
    def test_flat_coverage_and_size_are_reported(self) -> None:
        shots = [
            {
                "id": "s1",
                "beat_id": "b1",
                "coverage_role": "establish",
                "visible_change": "same",
                "shotSize": "medium",
                "dramatic_function": "hook",
                "duration_sec": 2,
            },
            {
                "id": "s2",
                "beat_id": "b1",
                "coverage_role": "establish",
                "visible_change": "same",
                "shotSize": "medium",
                "dramatic_function": "approach",
                "duration_sec": 3,
            },
            {
                "id": "s3",
                "beat_id": "b2",
                "coverage_role": "establish",
                "visible_change": "same",
                "shotSize": "medium",
                "dramatic_function": "action",
                "duration_sec": 3,
            },
            {
                "id": "s4",
                "beat_id": "b2",
                "coverage_role": "establish",
                "visible_change": "same",
                "shotSize": "medium",
                "dramatic_function": "action",
                "duration_sec": 3,
            },
        ]
        report = lint_rhythm(shots)
        self.assertFalse(report["ok"])
        self.assertIn("RHYTHM_COVERAGE_FLAT", report["codes"])
        self.assertIn("RHYTHM_SIZE_FLAT", report["codes"])

    def test_director_grammar_can_pass(self) -> None:
        shots = [
            {
                "id": "s1",
                "beat_id": "b1",
                "coverage_role": "context",
                "visible_change": "goal",
                "shotSize": "wide",
                "dramatic_function": "hook",
                "duration_sec": 2,
            },
            {
                "id": "s2",
                "beat_id": "b1",
                "coverage_role": "action",
                "visible_change": "obstacle",
                "shotSize": "medium",
                "dramatic_function": "approach",
                "duration_sec": 3,
            },
            {
                "id": "s3",
                "beat_id": "b2",
                "coverage_role": "reaction",
                "visible_change": "choice",
                "shotSize": "close-up",
                "dramatic_function": "reaction",
                "duration_sec": 3,
            },
            {
                "id": "s4",
                "beat_id": "b2",
                "coverage_role": "consequence",
                "visible_change": "cost",
                "shotSize": "medium",
                "dramatic_function": "afterglow",
                "duration_sec": 2,
            },
        ]
        self.assertTrue(lint_rhythm(shots)["ok"])


if __name__ == "__main__":
    unittest.main()
