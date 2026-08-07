"""Wave 2 · dialogue still recipe / no-speech prompt / audio_lane / cut_on."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class DialogueStillRecipeTests(unittest.TestCase):
    def test_safe_dialogue_mcu_ok(self) -> None:
        from dialogue_speaker_frame_gate import lint_dialogue_still_recipe

        r = lint_dialogue_still_recipe(
            {
                "id": "d1",
                "speaker": "heroine",
                "screen_mode": "on_camera",
                "shot_size": "mcu",
                "audio_cues": [{"spoken_text": "你好", "screen_mode": "on_camera"}],
            }
        )
        self.assertTrue(r["ok"])
        self.assertTrue(r["applies"])

    def test_wide_dialogue_hard(self) -> None:
        from dialogue_speaker_frame_gate import lint_dialogue_still_recipe

        r = lint_dialogue_still_recipe(
            {
                "id": "d2",
                "speaker": "heroine",
                "screen_mode": "on_camera",
                "shot_size": "fullbody",
                "audio_cues": [{"spoken_text": "过来", "screen_mode": "on_camera"}],
            }
        )
        self.assertFalse(r["ok"])
        codes = {i["code"] for i in r["issues"]}
        self.assertIn("DIALOGUE_STILL_WIDE_FRAME", codes)

    def test_missing_speaker_hard(self) -> None:
        from dialogue_speaker_frame_gate import lint_dialogue_still_recipe

        r = lint_dialogue_still_recipe(
            {
                "id": "d3",
                "screen_mode": "on_camera",
                "shot_size": "cu",
                "audio_cues": [{"spoken_text": "嗯", "screen_mode": "on_camera"}],
            }
        )
        self.assertFalse(r["ok"])
        codes = {i["code"] for i in r["issues"]}
        self.assertIn("SPEAKER_MISSING_FOR_STILL", codes)

    def test_register_assert_hard_adult(self) -> None:
        from dialogue_speaker_frame_gate import assert_dialogue_still_for_register
        from production_gates import ProductionGateError

        root = Path(tempfile.mkdtemp())
        (root / "film-spec.json").write_text(
            json.dumps(
                {
                    "vo_mode": "dialogue_drama",
                    "heat_scale": "max",
                    "genre": "adult",
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "s1",
                                    "screen_mode": "on_camera",
                                    "shot_size": "ws",
                                    "audio_cues": [
                                        {
                                            "spoken_text": "别停",
                                            "screen_mode": "on_camera",
                                        }
                                    ],
                                }
                            ]
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ProductionGateError) as ctx:
            assert_dialogue_still_for_register(root, "s1")
        self.assertIn("DIALOGUE_STILL_WIDE_FRAME", str(ctx.exception))


class DialoguePromptSpeechTests(unittest.TestCase):
    def test_no_speech_blocked(self) -> None:
        from dialogue_speaker_frame_gate import lint_dialogue_prompt_speech

        r = lint_dialogue_prompt_speech(
            "soft portrait, no speech, mouth closed",
            {
                "screen_mode": "on_camera",
                "spoken_text": "快点",
                "audio_cues": [{"spoken_text": "快点"}],
            },
        )
        self.assertFalse(r["ok"])
        self.assertIn("no speech", r["hits"])

    def test_spoken_prompt_ok(self) -> None:
        from dialogue_speaker_frame_gate import assert_dialogue_prompt_allows_speech

        r = assert_dialogue_prompt_allows_speech(
            "character speaks Mandarin clearly: 「快点」",
            {"spoken_text": "快点", "screen_mode": "on_camera"},
        )
        self.assertTrue(r["ok"])


class DialogueAudioLaneTests(unittest.TestCase):
    def test_apply_fills_native(self) -> None:
        from final.native_audio import (
            apply_film_dialogue_audio_lanes,
            lint_film_dialogue_audio_lanes,
        )

        spec = {
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "a",
                            "screen_mode": "on_camera",
                            "audio_cues": [{"spoken_text": "走"}],
                        }
                    ]
                }
            ]
        }
        before = lint_film_dialogue_audio_lanes(spec)
        self.assertFalse(before["ok"])
        apply_film_dialogue_audio_lanes(spec)
        after = lint_film_dialogue_audio_lanes(spec)
        self.assertTrue(after["ok"])
        self.assertEqual(spec["scenes"][0]["shots"][0]["dialogue_audio_lane"], "native")

    def test_explicit_lane_resolve(self) -> None:
        from final.native_audio import resolve_dialogue_audio_lane

        lane = resolve_dialogue_audio_lane(
            {"dialogue_audio_lane": "post_tts", "spoken_text": "hi"},
            has_native_stem=True,
            native_audible=True,
            has_spoken_text=True,
        )
        self.assertEqual(lane, "post_tts")


class DialogueCutOnTests(unittest.TestCase):
    def test_dialogue_gets_mid_motion_and_vo(self) -> None:
        from edit_policy import apply_shot_edit_rhythm_defaults, resolve_shot_visual_fit

        shot = {
            "id": "d",
            "screen_mode": "on_camera",
            "audio_cues": [{"spoken_text": "你好"}],
            "dramatic_function": "setup",
        }
        notes = apply_shot_edit_rhythm_defaults(shot)
        self.assertTrue(notes.get("cut_on_applied"))
        self.assertEqual(shot["dsl"]["cut_on"], "mid_motion")
        self.assertEqual(shot.get("visual_fit"), "vo")
        self.assertEqual(resolve_shot_visual_fit({"vo_mode": "dialogue_drama"}, shot), "vo")


class RestrictedDialogueLaneTests(unittest.TestCase):
    def test_shot_lane_dialogue_restricted_gates(self) -> None:
        from shot_lane import resolve_shot_lane

        r = resolve_shot_lane(
            {
                "id": "rd",
                "shot_role": "hero",
                "heat_phase": "act",
                "wardrobe_state": "bare",
                "screen_mode": "on_camera",
                "shot_size": "cu",
                "speaker": "heroine",
                "audio_cues": [{"spoken_text": "别停", "screen_mode": "on_camera"}],
            },
            intent={
                "content_class": "restricted_local",
                "spoken_text": "别停",
                "screen_mode": "on_camera",
            },
            has_still=True,
            has_last=False,
        )
        self.assertEqual(r["lane"], "dialogue_restricted")
        self.assertIn("speaker_frame", r["required_gates"])
        self.assertIn("dialogue_inject", r["required_gates"])
        self.assertEqual(r["h3_mode"], "i2v")


if __name__ == "__main__":
    unittest.main()
