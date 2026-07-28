"""Silk transitions, composition coverage, beat-suggested joins — shipped policy."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import edit_policy  # noqa: E402
from film_spec import validate_film_spec  # noqa: E402
from transition_ops import (  # noqa: E402
    TransitionOperationError,
    assert_hyperframes_safe_operations,
)


class SmoothTransitionDefaultsTests(unittest.TestCase):
    def test_default_transition_sec_is_silkier(self) -> None:
        self.assertGreaterEqual(edit_policy.DEFAULT_TRANSITION_SEC, 0.26)
        self.assertLessEqual(edit_policy.DEFAULT_TRANSITION_SEC, 0.40)

    def test_hold_longer_than_soft(self) -> None:
        soft = edit_policy.intent_to_base_sec("soft", 0.28)
        hold = edit_policy.intent_to_base_sec("hold", 0.28)
        hard = edit_policy.intent_to_base_sec("hard", 0.28)
        self.assertEqual(hard, 0.0)
        self.assertGreater(hold, soft)

    def test_suggest_join_shock_is_hard(self) -> None:
        self.assertEqual(edit_policy.suggest_join_intent("action", "reaction"), "hard")
        self.assertEqual(edit_policy.suggest_join_intent("sensory", "reaction"), "hard")

    def test_suggest_join_afterglow_is_hold(self) -> None:
        self.assertEqual(edit_policy.suggest_join_intent("reaction", "afterglow"), "hold")
        self.assertEqual(edit_policy.suggest_join_intent("action", "afterglow"), "hold")

    def test_suggest_transition_intents_length(self) -> None:
        beats = ["hook", "approach", "sensory", "action", "reaction", "afterglow"]
        joins = edit_policy.suggest_transition_intents(beats)
        self.assertEqual(len(joins), 5)
        self.assertEqual(joins[-1], "hold")  # → afterglow
        self.assertEqual(joins[-2], "hard")  # action → reaction


class CompositionCoverageTests(unittest.TestCase):
    def test_coverage_includes_angle_and_framing(self) -> None:
        for fn in ("hook", "sensory", "reaction", "action", "afterglow"):
            d = edit_policy.coverage_defaults_for_beat(fn)
            self.assertTrue(d["angle"])
            self.assertTrue(d["framing"])
            self.assertIn("9:16", d["framing"] + d.get("shot_size", ""))

    def test_apply_fills_framing_and_angle(self) -> None:
        shot = {"dsl": {"subject": "hero", "motion": "slow push-in, soft blink, idle not speaking"}}
        report = edit_policy.apply_coverage_defaults_to_shot(shot, dramatic_function="sensory")
        self.assertIn("dsl.camera.angle", report["filled"])
        self.assertIn("dsl.framing", report["filled"])
        self.assertEqual(shot["dsl"]["camera"]["shot_size"], "close-up")
        self.assertTrue(shot["dsl"]["camera"]["angle"])
        self.assertTrue(shot["dsl"]["framing"])

    def test_motion_templates_prefer_continuous_language(self) -> None:
        templates = edit_policy.i2v_motion_templates()
        for key in ("hook", "sensory", "approach", "action"):
            m = templates[key].lower()
            self.assertTrue(
                any(w in m for w in ("continuous", "smooth", "slow push", "dolly", "track")),
                msg=f"{key}: {m}",
            )
            edit_policy.validate_motion(templates[key])


class WriteSpecAutoJoinsTests(unittest.TestCase):
    def test_validate_auto_fills_transition_intents_and_sec(self) -> None:
        spec = {
            "title": "silk-test",
            "vo_mode": "storyteller",
            "director_intent": {
                "logline": "丝滑转场与构图默认验证用 logline。",
                "tone": "smooth",
                "emotional_arc": ["a", "b", "c"],
            },
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "shot01",
                            "dramatic_function": "hook",
                            "nar": "登场。",
                            "dsl": {
                                "subject": "a",
                                "motion": "slow push-in, soft blink, idle not speaking",
                            },
                        },
                        {
                            "id": "shot02",
                            "dramatic_function": "approach",
                            "nar": "靠近。",
                            "dsl": {
                                "subject": "a",
                                "motion": "dolly-in, breath, idle not speaking",
                            },
                        },
                        {
                            "id": "shot03",
                            "dramatic_function": "action",
                            "nar": "行动。",
                            "dsl": {
                                "subject": "a",
                                "motion": "body lean, track, idle not speaking",
                            },
                        },
                        {
                            "id": "shot04",
                            "dramatic_function": "reaction",
                            "nar": "反应。",
                            "dsl": {"subject": "a", "motion": "blink, flinch, idle not speaking"},
                        },
                        {
                            "id": "shot05",
                            "dramatic_function": "afterglow",
                            "nar": "余韵。",
                            "dsl": {
                                "subject": "a",
                                "motion": "hold look, breath, idle not speaking",
                            },
                        },
                    ]
                }
            ],
        }
        # no transition_intents / transition_sec in author spec
        shots = validate_film_spec(spec, assign_missing_ids=False)
        self.assertEqual(len(shots), 5)
        self.assertAlmostEqual(float(spec["transition_sec"]), edit_policy.DEFAULT_TRANSITION_SEC)
        # silk/cinematic fluency derives joins from edit_craft catalog
        self.assertEqual(spec.get("_transition_intents_source"), "edit_craft")
        self.assertEqual(spec.get("_edit_craft_source"), "craft_suggest")
        intents = spec["transition_intents"]
        crafts = spec.get("edit_craft") or []
        self.assertEqual(len(intents), 4)
        self.assertEqual(len(crafts), 4)
        ops = spec.get("transition_ops") or []
        self.assertEqual(len(ops), 4)
        self.assertEqual(ops[0]["from_shot"], "shot01")
        self.assertEqual(ops[0]["to_shot"], "shot02")
        self.assertIn(ops[0]["picture"]["base"], {"hard_cut", "xfade"})
        # action → reaction should be hard (smash / impact family)
        self.assertEqual(intents[2], "hard")
        # → afterglow: craft catalog may use contrast_cut (hard) rather than pure hold
        self.assertIn(intents[3], {"hold", "hard", "soft"})
        self.assertTrue(crafts[3])
        # sensory composition filled
        self.assertTrue(shots[0]["dsl"]["camera"].get("angle"))
        self.assertTrue(shots[0]["dsl"].get("framing") or shots[0]["dsl"]["camera"].get("framing"))

    def test_continue_operation_forces_hard_cut_and_preserves_reason(self) -> None:
        spec = {
            "title": "continue-op",
            "vo_mode": "storyteller",
            "director_intent": {
                "logline": "连续动作的转场操作验证。",
                "tone": "drama",
                "emotional_arc": ["a", "b", "c"],
            },
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "a",
                            "dramatic_function": "approach",
                            "nar": "抬手。",
                            "dsl": {"subject": "hero", "motion": "pan, idle not speaking"},
                        },
                        {
                            "id": "b",
                            "dramatic_function": "action",
                            "nar": "承接。",
                            "dsl": {
                                "subject": "hero",
                                "motion": "track, idle not speaking",
                                "chain_mode": "continue",
                                "cut_on": "mid_motion",
                            },
                        },
                    ]
                }
            ],
            "transition_ops": [{"locked": True, "reason": "必须保持手势连续"}],
        }
        validate_film_spec(spec, assign_missing_ids=False)
        op = spec["transition_ops"][0]
        self.assertEqual(op["type"], "cut_on_action")
        self.assertEqual(op["picture"]["base"], "hard_cut")
        self.assertEqual(op["picture"]["duration_sec"], 0.0)
        self.assertTrue(op["locked"])
        self.assertEqual(op["reason"], "必须保持手势连续")

    def test_transition_author_metadata_requires_declared_types(self) -> None:
        spec = {
            "title": "invalid-op-metadata",
            "vo_mode": "storyteller",
            "director_intent": {
                "logline": "人工转场锁定字段型别验证。",
                "tone": "drama",
                "emotional_arc": ["a", "b", "c"],
            },
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "a",
                            "dramatic_function": "hook",
                            "nar": "开始。",
                            "dsl": {"subject": "hero", "motion": "hold, idle not speaking"},
                        },
                        {
                            "id": "b",
                            "dramatic_function": "reaction",
                            "nar": "反应。",
                            "dsl": {"subject": "hero", "motion": "hold, idle not speaking"},
                        },
                    ]
                }
            ],
            "transition_ops": [{"locked": "false", "reason": 123}],
        }
        with self.assertRaisesRegex(Exception, "locked must be boolean"):
            validate_film_spec(spec, assign_missing_ids=False)

    def test_hyperframes_safety_rejects_continue_overlay(self) -> None:
        with self.assertRaisesRegex(TransitionOperationError, "continue seam"):
            assert_hyperframes_safe_operations(
                [
                    {
                        "continuity_class": "continue",
                        "picture": {
                            "base": "hard_cut",
                            "duration_sec": 0,
                            "hyperframes_overlay": "light_leak",
                        },
                    }
                ]
            )

    def test_normalize_xfade_style(self) -> None:
        self.assertEqual(edit_policy.normalize_xfade_style(None), "fade")
        self.assertEqual(edit_policy.normalize_xfade_style("smoothleft"), "smoothleft")
        with self.assertRaises(edit_policy.PolicyError):
            edit_policy.normalize_xfade_style("not_a_style")


if __name__ == "__main__":
    unittest.main()
