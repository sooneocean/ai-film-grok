"""BGM mood defaults: 色气 → rnb, never horror dark by accident."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from film_spec import validate_film_spec  # noqa: E402
from sound_plan import (  # noqa: E402
    default_sound_plan_for_film,
    normalize_sound_mood,
    validate_sound_plan,
)


def _spec(tone: str, sound_plan=None) -> dict:
    s = {
        "title": "Kei后宫",
        "description": "暗黑同人里番",
        "vo_mode": "storyteller",
        "director_intent": {
            "logline": "银白仿生少女掠夺教师后宫。",
            "tone": tone,
            "emotional_arc": ["抓现行", "崩坏", "后宫"],
        },
        "scenes": [
            {
                "shots": [
                    {
                        "id": "shot01",
                        "dramatic_function": "hook",
                        "duration_sec": 6,
                        "nar": "夜深社办。她外套大敞。",
                        "dsl": {
                            "subject": "kei",
                            "action": "sits",
                            "motion": "slow push-in, soft blink, idle not speaking",
                        },
                    }
                ]
            }
        ],
    }
    if sound_plan is not None:
        s["sound_plan"] = sound_plan
    return s


class SoundPlanMoodTests(unittest.TestCase):
    def test_soul_alias_is_rnb(self) -> None:
        self.assertEqual(normalize_sound_mood("soul"), "rnb")
        self.assertEqual(normalize_sound_mood("R&B"), "rnb")

    def test_default_for_ecchi_is_rnb(self) -> None:
        d = default_sound_plan_for_film(tone="快节奏暗黑同人里番", vo_mode="storyteller")
        self.assertEqual(d["mood"], "rnb")

    def test_dark_auto_rewritten_for_ecchi_tone(self) -> None:
        plan = validate_sound_plan(
            {"mood": "dark", "bed": True},
            tone="色气·里番",
            title="Kei后宫",
        )
        assert plan is not None
        self.assertEqual(plan["mood"], "rnb")
        self.assertTrue(plan.get("_notes"))

    def test_write_spec_injects_rnb_when_missing(self) -> None:
        spec = _spec("色气里番诱惑")
        validate_film_spec(spec, assign_missing_ids=False)
        self.assertEqual(spec["sound_plan"]["mood"], "rnb")

    def test_write_spec_rewrites_dark_on_ecchi(self) -> None:
        spec = _spec("暗黑同人里番", sound_plan={"mood": "dark", "bed": True})
        validate_film_spec(spec, assign_missing_ids=False)
        self.assertEqual(spec["sound_plan"]["mood"], "rnb")

    def test_horror_tone_gets_dark_not_rnb(self) -> None:
        """Genre migration test (2026-07-22): horror storyteller film must
        get 'dark', not the storyteller-default 'rnb'."""
        d = default_sound_plan_for_film(tone="恐怖·惊悚", vo_mode="storyteller")
        self.assertEqual(d["mood"], "dark")

    def test_horror_in_title_gets_dark(self) -> None:
        d = default_sound_plan_for_film(tone="悬疑", title="走廊尽头的病房", vo_mode="storyteller")
        self.assertEqual(d["mood"], "dark")

    def test_horror_dark_not_rewritten_by_ecchi_check(self) -> None:
        """A horror tone explicitly asking for dark should keep it
        (tone_implies_ecchi is False for horror, so no rewrite)."""
        plan = validate_sound_plan(
            {"mood": "dark", "bed": True},
            tone="恐怖",
            title="走廊尽头的病房",
        )
        assert plan is not None
        self.assertEqual(plan["mood"], "dark")


if __name__ == "__main__":
    unittest.main()
