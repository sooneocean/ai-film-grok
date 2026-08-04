"""Director intent + dramatic_function — shipped film_spec validation path."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from film_spec import (  # noqa: E402
    DRAMATIC_FUNCTIONS,
    FilmSpecError,
    validate_film_spec,
)


def _minimal_valid() -> dict:
    return {
        "title": "intent-test",
        "vo_mode": "storyteller",
        "dramatic_meaning_strict": False,
        "director_intent": {
            "logline": "雨夜后座升温的完整承诺句。",
            "tone": "色气·压迫",
            "emotional_arc": ["hook-beat", "rise", "afterglow"],
            "audience": "完播观众",
            "taboos": ["说教收尾"],
        },
        "scenes": [
            {
                "shots": [
                    {
                        "id": "shot01",
                        "dramatic_function": "hook",
                        "nar": "话说夜里。",
                        "dsl": {
                            "subject": "woman",
                            "action": "looks",
                            "motion": "slow push-in, soft blink, idle not speaking",
                        },
                    }
                ]
            }
        ],
    }


class DirectorIntentValidationTests(unittest.TestCase):
    def test_missing_director_intent_fails(self) -> None:
        spec = _minimal_valid()
        del spec["director_intent"]
        with self.assertRaisesRegex(FilmSpecError, "director_intent"):
            validate_film_spec(spec, assign_missing_ids=False)

    def test_short_logline_fails(self) -> None:
        spec = _minimal_valid()
        spec["director_intent"]["logline"] = "短"
        with self.assertRaisesRegex(FilmSpecError, "logline"):
            validate_film_spec(spec, assign_missing_ids=False)

    def test_emotional_arc_too_short_fails(self) -> None:
        spec = _minimal_valid()
        spec["director_intent"]["emotional_arc"] = ["a", "b"]
        with self.assertRaisesRegex(FilmSpecError, "emotional_arc"):
            validate_film_spec(spec, assign_missing_ids=False)

    def test_missing_dramatic_function_fails(self) -> None:
        spec = _minimal_valid()
        del spec["scenes"][0]["shots"][0]["dramatic_function"]
        with self.assertRaisesRegex(FilmSpecError, "dramatic_function"):
            validate_film_spec(spec, assign_missing_ids=False)

    def test_invalid_dramatic_function_fails(self) -> None:
        spec = _minimal_valid()
        spec["scenes"][0]["shots"][0]["dramatic_function"] = "pretty_frame"
        with self.assertRaisesRegex(FilmSpecError, "dramatic_function"):
            validate_film_spec(spec, assign_missing_ids=False)

    def test_valid_normalizes_function_and_intent(self) -> None:
        spec = _minimal_valid()
        spec["scenes"][0]["shots"][0]["dramatic_function"] = "  HOOK  "
        shots = validate_film_spec(spec, assign_missing_ids=False)
        self.assertEqual(len(shots), 1)
        self.assertEqual(shots[0]["dramatic_function"], "hook")
        self.assertIn("hook", DRAMATIC_FUNCTIONS)
        self.assertEqual(spec["director_intent"]["logline"].startswith("雨夜"), True)

    def test_shipped_example_template_validates(self) -> None:
        path = ROOT / "templates" / "film-spec.example.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        shots = validate_film_spec(copy.deepcopy(data), assign_missing_ids=False)
        self.assertGreaterEqual(len(shots), 1)
        self.assertIn(shots[0]["dramatic_function"], DRAMATIC_FUNCTIONS)
        intent = data["director_intent"]
        self.assertGreaterEqual(len(intent["emotional_arc"]), 3)


if __name__ == "__main__":
    unittest.main()
