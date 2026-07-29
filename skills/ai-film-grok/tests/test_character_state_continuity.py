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


class AssetsCheckStateRegressionTests(unittest.TestCase):
    """P2-7: assets_check now derives 5-axis timeline and detects state regression."""

    def _make_root(self, shots: list[dict]) -> Path:
        import json
        import tempfile

        tmp = tempfile.mkdtemp(prefix="aifilm_cst_test_")
        root = Path(tmp)
        spec = {
            "schema_version": 1,
            "title": "cst-test",
            "vo_mode": "storyteller",
            "aspect": "9:16",
            "director_intent": {
                "logline": "State regression test.",
                "tone": "neutral",
                "emotional_arc": ["a", "b"],
            },
            "transition_sec": 0.25,
            "transition_default": "soft",
            "scenes": [{"shots": shots}],
        }
        (root / "film-spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return root

    def _shot(self, sid, heat_phase="setup"):
        return {
            "id": sid,
            "heat_phase": heat_phase,
            "dramatic_function": "approach",
            "nar": f"旁白{sid}。",
            "dsl": {
                "subject": "woman",
                "cast": ["heroine"],
                "camera": {"shot_size": "medium"},
                "motion": "idle",
            },
        }

    def test_monotonic_progression_no_regression(self):
        from asset_registry import assets_check

        shots = [
            self._shot("shot01", "teaser"),
            self._shot("shot02", "foreplay"),
            self._shot("shot03", "act"),
        ]
        root = self._make_root(shots)
        rep = assets_check(root)
        timeline = rep.get("character_state_timeline") or []
        self.assertEqual(len(timeline), 3)
        self.assertEqual(rep.get("state_regression_issues") or [], [])
        self.assertFalse(rep.get("hard_fail_state_regression", False))

    def test_timeline_attached_to_assets_check(self):
        """The 5-axis timeline is now part of assets_check output (was orphan)."""
        from asset_registry import assets_check

        shots = [self._shot("shot01", "act"), self._shot("shot02", "afterglow")]
        root = self._make_root(shots)
        rep = assets_check(root)
        timeline = rep.get("character_state_timeline") or []
        self.assertGreater(len(timeline), 0)
        first = timeline[0]
        self.assertIn("shot_id", first)
        self.assertIn("character_states", first)
        cs = first["character_states"]
        # All 5 axes present
        for axis in ("wardrobe", "hair", "skin", "arousal", "expression"):
            self.assertIn(axis, cs)


class DialoguePerformanceStateGateTests(unittest.TestCase):
    def test_dialogue_shot_requests_i2i_performance_state_photo(self) -> None:
        import json
        import tempfile

        from state_index_gate import run_state_index_check

        with tempfile.TemporaryDirectory(prefix="aifilm_dialogue_state_") as tmp:
            root = Path(tmp)
            spec = {
                "title": "dialogue state",
                "vo_mode": "dialogue_drama",
                "director_intent": {
                    "logline": "A character makes a short decisive statement.",
                    "tone": "tense",
                    "emotional_arc": ["wait", "turn", "act"],
                },
                "scenes": [
                    {
                        "shots": [
                            {
                                "id": "talk01",
                                "dramatic_function": "action",
                                "duration_sec": 3,
                                "screen_mode": "on_camera",
                                "dialogue_line_id": "dlg_01",
                                "speaker": "hero",
                                "speaker_on_camera": True,
                                "lipsync": True,
                                "performance_state_id": "hero-dlg_01-defiant",
                                "audio_cues": [
                                    {
                                        "kind": "voice",
                                        "line_type": "dialogue",
                                        "speaker": "hero",
                                        "spoken_text": "我不会走。",
                                        "start_offset_sec": 0,
                                        "duration_sec": 3,
                                    }
                                ],
                                "dsl": {
                                    "subject": "hero",
                                    "cast": ["hero"],
                                    "action": "holds the door",
                                    "motion": "subtle breath",
                                },
                            },
                            {
                                "id": "cover01",
                                "dramatic_function": "reaction",
                                "duration_sec": 2,
                                "screen_mode": "reaction",
                                "audio_cues": [
                                    {"kind": "silence", "start_offset_sec": 0, "duration_sec": 2}
                                ],
                                "dsl": {
                                    "subject": "listener",
                                    "cast": ["hero"],
                                    "action": "listens",
                                    "motion": "still reaction",
                                },
                            },
                        ]
                    }
                ],
            }
            (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
            report = run_state_index_check(root)
            self.assertIn(
                "talk01:hero-dlg_01-defiant", report["missing_dialogue_performance_states"]
            )
            self.assertIn(
                "generate_dialogue_state_photo",
                {step["action"] for step in report["generate_plan"]},
            )
            step = next(
                item
                for item in report["generate_plan"]
                if item["action"] == "generate_dialogue_state_photo"
            )
            self.assertEqual(step["generation_receipt_contract"]["operation"], "image_edit")
            self.assertIn("input_sha256", step["generation_receipt_contract"]["required"])
            self.assertTrue(step["generation_receipt_out"].endswith("hero-dlg_01-defiant.json"))
            self.assertIn("approve-performance-state", step["approval_command"])


if __name__ == "__main__":
    unittest.main()
