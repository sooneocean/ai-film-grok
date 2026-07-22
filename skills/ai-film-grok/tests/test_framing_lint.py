"""Framing iron lint (cn sediment) on write-spec / film_spec path."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from film_spec import FilmSpecError, validate_film_spec  # noqa: E402
from framing_lint import (  # noqa: E402
    framing_crop_risk_in_text,
    lint_framing_iron,
)


def _minimal(*, framing: str | None = None, motion: str | None = None) -> dict:
    dsl: dict = {
        "subject": "woman",
        "action": "turns latch",
        "motion": motion or "hand turns latch shut, body angles in, idle not speaking",
    }
    if framing is not None:
        dsl["framing"] = framing
    return {
        "title": "framing-lint-test",
        "vo_mode": "storyteller",
        "director_intent": {
            "logline": "雨夜后座升温的完整承诺句。",
            "tone": "色气",
            "emotional_arc": ["hook", "rise", "after"],
        },
        "scenes": [
            {
                "shots": [
                    {
                        "id": "shot01",
                        "dramatic_function": "hook",
                        "nar": "话说她落锁。",
                        "dsl": dsl,
                    }
                ]
            }
        ],
    }


class FramingLintTests(unittest.TestCase):
    def test_crop_prone_text_detected(self) -> None:
        hits = framing_crop_risk_in_text("extreme close-up, face fills the frame, push-in on face")
        self.assertTrue(hits)
        self.assertTrue(any("extreme" in h.lower() or "fill" in h.lower() for h in hits))

    def test_lint_flags_crop_prone_framing(self) -> None:
        shots = [
            {
                "id": "shot01",
                "dramatic_function": "hook",
                "dsl": {
                    "framing": "extreme close-up, top of head cropped, no headroom",
                    "motion": "push-in on face",
                },
            }
        ]
        report = lint_framing_iron(shots)
        self.assertFalse(report["ok"])
        self.assertIn("FRAMING_CROP_RISK", report["codes"])
        self.assertGreater(report["warning_count"], 0)

    def test_safe_framing_passes(self) -> None:
        shots = [
            {
                "id": "shot01",
                "dramatic_function": "hook",
                "dsl": {
                    "framing": (
                        "medium shot waist-up, full head and both shoulders inside frame, "
                        "ample headroom, safe framing no cropping, subject stays framed"
                    ),
                    "motion": "hand turns latch, body angles in",
                },
            }
        ]
        report = lint_framing_iron(shots)
        self.assertTrue(report["ok"])
        self.assertEqual(report["warning_count"], 0)

    def test_write_spec_path_emits_framing_lint(self) -> None:
        spec = _minimal(
            framing="extreme close-up, detail fills frame, push-in on face",
        )
        shots = validate_film_spec(spec, assign_missing_ids=False)
        self.assertEqual(len(shots), 1)
        lint = spec.get("_framing_lint")
        self.assertIsInstance(lint, dict)
        self.assertIn("FRAMING_CROP_RISK", lint.get("codes") or [])
        self.assertFalse(lint.get("ok"))

    def test_framing_strict_hard_fails(self) -> None:
        spec = _minimal(
            framing="extreme close-up, face fills the frame",
        )
        spec["framing_strict"] = True
        with self.assertRaisesRegex(FilmSpecError, "framing"):
            validate_film_spec(spec, assign_missing_ids=False)

    def test_default_coverage_not_crop_prone(self) -> None:
        """Coverage defaults must not inject fill-frame crop language."""
        spec = _minimal(framing=None)
        # no explicit framing → coverage injects defaults
        shots = validate_film_spec(spec, assign_missing_ids=False)
        lint = spec.get("_framing_lint") or {}
        # soft headroom miss ok; crop risk from defaults must be absent
        codes = lint.get("codes") or []
        self.assertNotIn("FRAMING_CROP_RISK", codes)
        framing = (shots[0].get("dsl") or {}).get("framing") or ""
        import re

        self.assertIsNone(re.search(r"fills?\s+(the\s+)?frame", framing, re.I))


if __name__ == "__main__":
    unittest.main()
