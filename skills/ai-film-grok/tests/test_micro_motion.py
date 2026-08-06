"""Beat micro-motion injection — shipped edit_policy helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from edit_policy import (  # noqa: E402
    apply_coverage_defaults_to_shot,
    inject_micro_motion_cues,
)
from film_spec import validate_film_spec  # noqa: E402


class MicroMotionTests(unittest.TestCase):
    def test_inject_adds_cues_for_reaction_without_micro(self) -> None:
        raw = "looks at camera, idle not speaking"
        out = inject_micro_motion_cues(raw, "reaction")
        self.assertNotEqual(out, raw)
        lowered = out.lower()
        self.assertTrue(
            any(k in lowered for k in ("blink", "tremble", "push-in", "breath")),
            msg=out,
        )

    def test_inject_noop_when_blink_already_present(self) -> None:
        raw = "soft blink, slow pan, idle not speaking"
        out = inject_micro_motion_cues(raw, "sensory")
        self.assertEqual(out, raw)

    def test_inject_for_sensory_and_afterglow(self) -> None:
        for beat in ("sensory", "afterglow"):
            out = inject_micro_motion_cues("static hold on face", beat)
            self.assertIn("blink", out.lower())

    def test_action_beat_does_not_force_suffix(self) -> None:
        raw = "walks forward, fabric sway"
        out = inject_micro_motion_cues(raw, "action")
        self.assertEqual(out, raw)

    def test_apply_coverage_injects_on_author_motion(self) -> None:
        shot = {
            "id": "shot01",
            "dsl": {
                "subject": "woman",
                "action": "reacts",
                "motion": "looks away, idle not speaking",
            },
        }
        report = apply_coverage_defaults_to_shot(shot, dramatic_function="reaction")
        self.assertTrue(
            report.get("micro_motion_injected")
            or "dsl.motion_micro_inject" in report.get("filled", [])
        )
        self.assertIn("blink", shot["dsl"]["motion"].lower())

    def test_write_spec_path_injects_via_validate_film_spec(self) -> None:
        spec = {
            "title": "micro-motion-spec",
            "vo_mode": "storyteller",
            "dramatic_meaning_strict": False,
            "director_intent": {
                "logline": "近景反应也要有可见微动。",
                "tone": "测试",
                "emotional_arc": ["a", "b", "c"],
            },
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "shot01",
                            "dramatic_function": "reaction",
                            "nar": "她愣住了。",
                            "dsl": {
                                "subject": "woman",
                                "action": "stares",
                                "motion": "looks at him, idle not speaking",
                            },
                        }
                    ]
                }
            ],
        }
        shots = validate_film_spec(spec, assign_missing_ids=False)
        motion = shots[0]["dsl"]["motion"].lower()
        self.assertTrue(
            any(k in motion for k in ("blink", "tremble", "push-in", "breath")),
            msg=motion,
        )


if __name__ == "__main__":
    unittest.main()
