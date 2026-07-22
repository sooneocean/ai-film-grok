"""B1 coverage defaults + B2 director scorecard (shipped entry points)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import director_review  # noqa: E402
import edit_policy  # noqa: E402
from film_spec import validate_film_spec  # noqa: E402


class BeatCoverageDefaultsTests(unittest.TestCase):
    def test_every_dramatic_function_has_coverage_defaults(self) -> None:
        from film_spec import DRAMATIC_FUNCTIONS

        for fn in sorted(DRAMATIC_FUNCTIONS):
            d = edit_policy.coverage_defaults_for_beat(fn)
            self.assertEqual(d["dramatic_function"], fn)
            self.assertTrue(d["shot_size"])
            self.assertTrue(d["motion"])
            # must pass motion validation
            edit_policy.validate_motion(d["motion"])

    def test_apply_fills_only_missing_fields(self) -> None:
        shot = {"dsl": {"subject": "a", "motion": "slow pan, blink, idle not speaking"}}
        report = edit_policy.apply_coverage_defaults_to_shot(shot, dramatic_function="sensory")
        # motion author wins; missing camera/framing are filled
        self.assertIn("dsl.camera.shot_size", report["filled"])
        self.assertIn("dsl.camera.angle", report["filled"])
        self.assertIn("dsl.framing", report["filled"])
        self.assertNotIn("dsl.motion", report["filled"])
        self.assertEqual(shot["dsl"]["camera"]["shot_size"], "close-up")
        self.assertEqual(shot["dsl"]["motion"], "slow pan, blink, idle not speaking")

    def test_validate_film_spec_sensory_default_is_closeup(self) -> None:
        spec = {
            "title": "cov",
            "vo_mode": "storyteller",
            "director_intent": {
                "logline": "感官特写默认景别测试用 logline。",
                "tone": "test",
                "emotional_arc": ["a", "b", "c"],
            },
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "shot01",
                            "dramatic_function": "sensory",
                            "nar": "特写。",
                            "dsl": {"subject": "collarbone"},
                        }
                    ]
                }
            ],
        }
        shots = validate_film_spec(spec, assign_missing_ids=False)
        self.assertEqual(shots[0]["dsl"]["camera"]["shot_size"], "close-up")
        self.assertIn("push", shots[0]["dsl"]["motion"].lower())


class DirectorScorecardTests(unittest.TestCase):
    def test_all_pass_required(self) -> None:
        card = {d: True for d in director_review.SCORECARD_DIMENSIONS}
        out = director_review.validate_scorecard_for_approve(card)
        self.assertTrue(out["all_pass"])
        card["dead_air"] = False
        with self.assertRaisesRegex(director_review.DirectorReviewError, "dead_air"):
            director_review.validate_scorecard_for_approve(card)

    def test_cli_builder_requires_all_flags(self) -> None:
        args = SimpleNamespace(**{f"score_{d}": None for d in director_review.SCORECARD_DIMENSIONS})
        with self.assertRaisesRegex(director_review.DirectorReviewError, "scorecard"):
            director_review.build_scorecard_from_cli(args)
        for d in director_review.SCORECARD_DIMENSIONS:
            setattr(args, f"score_{d}", "pass")
        card = director_review.build_scorecard_from_cli(args)
        self.assertTrue(all(card.values()))

    def test_legacy_review_without_scorecard_fails_gate_check(self) -> None:
        self.assertFalse(
            director_review.scorecard_is_complete_and_passing({"approved": True, "notes": "lgtm"})
        )
        self.assertTrue(
            director_review.scorecard_is_complete_and_passing(
                {
                    "scorecard": {
                        "dimensions": {d: True for d in director_review.SCORECARD_DIMENSIONS}
                    }
                }
            )
        )


class DirectorNotesReshootLoopTests(unittest.TestCase):
    def test_build_notes_from_scorecard_attaches_shots_for_motion_fail(self) -> None:
        card = {d: True for d in director_review.SCORECARD_DIMENSIONS}
        card["motion"] = False
        card["identity"] = False
        package = director_review.build_notes_from_scorecard_failures(
            card,
            notes_text="faces drift",
            output_sha256="abc",
            shot_ids=["shot01", "shot03"],
        )
        open_items = director_review.open_reshoot_items(package)
        # identity + motion × 2 shots
        self.assertEqual(len(open_items), 4)
        self.assertTrue(all(i["action"] == "reshoot" for i in open_items))
        self.assertEqual({i["shot_id"] for i in open_items}, {"shot01", "shot03"})

    def test_resolve_and_reshoots_clear(self) -> None:
        notes = director_review.empty_director_notes()
        director_review.add_reshoot_item(
            notes, action="reshoot", reason_code="motion", shot_id="shot01", note="warp"
        )
        self.assertFalse(director_review.reshoots_clear(notes))
        director_review.resolve_reshoot_item(notes, shot_id="shot01", resolve_note="regen ok")
        self.assertTrue(director_review.reshoots_clear(notes))
        self.assertIsNotNone(notes.get("closed_at"))


if __name__ == "__main__":
    unittest.main()
