"""Speaker ↔ picture contract for on_camera dialogue."""

from __future__ import annotations

import unittest

from dialogue_speaker_frame_gate import (
    assert_dialogue_speaker_frame_contract,
    lint_dialogue_speaker_frame,
)
from production_gates import ProductionGateError


def _spec(shots, **kw):
    base = {
        "title": "sf",
        "vo_mode": "dialogue_drama",
        "heat_scale": "max",
        "cast": {"mei": {"name": "mei"}, "ken": {"name": "ken"}},
        "director_intent": {"protagonist_want": "truth", "emotional_arc": ["hook", "climax"]},
        "scenes": [{"shots": shots}],
        "dramatic_meaning_strict": False,
    }
    base.update(kw)
    return base


class SpeakerFrameTests(unittest.TestCase):
    def test_good_on_camera_passes(self) -> None:
        spec = _spec(
            [
                {
                    "id": "s1",
                    "screen_mode": "on_camera",
                    "speaker": "mei",
                    "heat_phase": "act",
                    "beat_id": "b1",
                    "dsl": {"subject": "mei close-up speaking", "action": "speaks"},
                    "audio_cues": [
                        {
                            "spoken_text": "别停",
                            "speaker": "mei",
                            "screen_mode": "on_camera",
                        }
                    ],
                }
            ]
        )
        r = lint_dialogue_speaker_frame(spec)
        self.assertTrue(r["ok"], r)

    def test_subject_mismatch_flags(self) -> None:
        spec = _spec(
            [
                {
                    "id": "s1",
                    "screen_mode": "on_camera",
                    "speaker": "mei",
                    "heat_phase": "act",
                    "dsl": {"subject": "ken body only", "action": "thrusts"},
                    "audio_cues": [
                        {"spoken_text": "嗯", "speaker": "mei", "screen_mode": "on_camera"}
                    ],
                }
            ]
        )
        r = lint_dialogue_speaker_frame(spec)
        codes = {v["code"] for v in r["violations"]}
        self.assertIn("SPEAKER_NOT_IN_SUBJECT", codes)

    def test_window_flip_hard(self) -> None:
        spec = _spec(
            [
                {
                    "id": "a",
                    "screen_mode": "on_camera",
                    "speaker": "mei",
                    "heat_phase": "act",
                    "beat_id": "same",
                    "dsl": {"subject": "mei face"},
                    "audio_cues": [
                        {"spoken_text": "一", "speaker": "mei", "screen_mode": "on_camera"}
                    ],
                },
                {
                    "id": "b",
                    "screen_mode": "on_camera",
                    "speaker": "ken",
                    "heat_phase": "act",
                    "beat_id": "same",
                    "dsl": {"subject": "ken face"},
                    "audio_cues": [
                        {"spoken_text": "二", "speaker": "ken", "screen_mode": "on_camera"}
                    ],
                },
            ],
            dialogue_window_strict=True,
        )
        with self.assertRaises(ProductionGateError):
            assert_dialogue_speaker_frame_contract(spec=spec, hard=True)


if __name__ == "__main__":
    unittest.main()
