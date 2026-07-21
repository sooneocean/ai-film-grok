"""VO budget hard gate on shipped film_spec.validate_film_spec path."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from film_spec import (  # noqa: E402
    MAX_NAR_CHARS,
    RECOMMENDED_NAR_CHARS,
    FilmSpecError,
    estimate_nar_vo_sec,
    validate_film_spec,
    validate_nar_budget,
)


def _minimal(nar: str) -> dict:
    return {
        "title": "vo-budget-test",
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
                        "nar": nar,
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


class VoBudgetTests(unittest.TestCase):
    def test_short_nar_passes_and_sets_est_vo(self) -> None:
        nar = "话说夜里，她把门拉开。"
        shots = validate_film_spec(_minimal(nar), assign_missing_ids=False)
        self.assertEqual(shots[0]["nar"], nar)
        self.assertIn("est_vo_sec", shots[0])
        self.assertGreater(shots[0]["est_vo_sec"], 0)
        self.assertLessEqual(len(nar), MAX_NAR_CHARS)

    def test_long_nar_fails_with_vo_budget_signal(self) -> None:
        # 56+ Chinese-ish chars (use ASCII for stable length)
        long_nar = "A" * (MAX_NAR_CHARS + 1)
        with self.assertRaisesRegex(FilmSpecError, "vo_budget"):
            validate_film_spec(_minimal(long_nar), assign_missing_ids=False)

    def test_validate_nar_budget_direct(self) -> None:
        ok = validate_nar_budget("短旁白即可。", field="shot01.nar")
        self.assertIn("短旁白", ok)
        with self.assertRaisesRegex(FilmSpecError, "vo_budget"):
            validate_nar_budget("x" * (MAX_NAR_CHARS + 5), field="shot02.nar")

    def test_estimate_nar_vo_sec_scales_with_length(self) -> None:
        short = estimate_nar_vo_sec("你好")
        long = estimate_nar_vo_sec("你" * 40)
        self.assertGreaterEqual(long, short)
        self.assertGreaterEqual(short, 1.0)

    def test_max_boundary_exactly_max_passes(self) -> None:
        boundary = "B" * MAX_NAR_CHARS
        spec = _minimal(boundary)
        # est_vo=13.75 needs duration covering vo_pacing hard gate
        spec["scenes"][0]["shots"][0]["duration_sec"] = 14
        shots = validate_film_spec(spec, assign_missing_ids=False)
        self.assertEqual(len(shots[0]["nar"]), MAX_NAR_CHARS)

    def test_recommended_constant_below_max(self) -> None:
        self.assertLess(RECOMMENDED_NAR_CHARS, MAX_NAR_CHARS)
        # Snappy default after Kei loop-boredom lesson
        self.assertLessEqual(RECOMMENDED_NAR_CHARS, 32)

    def test_vo_pacing_hard_fails_when_est_exceeds_duration(self) -> None:
        # ~40 chars → est_vo ≈ 10s > duration_sec 6 + slack
        nar = "字" * 40
        spec = _minimal(nar)
        spec["scenes"][0]["shots"][0]["duration_sec"] = 6
        with self.assertRaisesRegex(FilmSpecError, "vo_pacing"):
            validate_film_spec(spec, assign_missing_ids=False)

    def test_vo_pacing_passes_when_duration_covers_est(self) -> None:
        nar = "字" * 40  # est ≈ 10s
        spec = _minimal(nar)
        spec["scenes"][0]["shots"][0]["duration_sec"] = 10
        shots = validate_film_spec(spec, assign_missing_ids=False)
        self.assertEqual(float(shots[0]["duration_sec"]), 10.0)
        self.assertLessEqual(float(shots[0]["est_vo_sec"]), 10.5)

    def test_default_duration_applied_and_short_nar_ok(self) -> None:
        nar = "话说夜里，她把门拉开。"  # short enough for 6s
        shots = validate_film_spec(_minimal(nar), assign_missing_ids=False)
        self.assertEqual(float(shots[0]["duration_sec"]), 6.0)
        self.assertLessEqual(float(shots[0]["est_vo_sec"]), 6.5)


if __name__ == "__main__":
    unittest.main()
