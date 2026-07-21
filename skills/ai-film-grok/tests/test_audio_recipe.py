"""Scene-adaptive audio_policy + audio_recipe routing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audio_recipe import (  # noqa: E402
    apply_audio_recipes_to_spec,
    default_audio_policy,
    resolve_shot_audio_recipe,
    suggest_recipe_for_shot,
    validate_audio_policy,
)


class AudioRecipeTests(unittest.TestCase):
    def test_policy_auto_never_sung(self) -> None:
        p = default_audio_policy(vo_mode="storyteller")
        self.assertEqual(p["mode"], "auto")
        self.assertFalse(p["allow_sung"])

    def test_policy_musical_hybrid_allows_sung(self) -> None:
        p = validate_audio_policy({"mode": "musical_hybrid"}, vo_mode="hybrid")
        self.assertTrue(p["allow_sung"])
        self.assertEqual(p["max_sung_shots"], 1)

    def test_sensory_short_nar_bed_focus(self) -> None:
        shot = {
            "id": "s1",
            "dramatic_function": "sensory",
            "nar": "呼吸很近。",
            "camera": {"shot_size": "cu"},
        }
        policy = default_audio_policy()
        r, reasons = suggest_recipe_for_shot(
            shot, policy=policy, vo_mode="storyteller", index=2, n_shots=6, sung_slots_left=0
        )
        self.assertEqual(r, "bed_focus")
        self.assertTrue(any("sensory" in x or "bed_focus" in x for x in reasons))

    def test_hook_is_narrate_bed(self) -> None:
        shot = {
            "id": "s1",
            "dramatic_function": "hook",
            "nar": "雨夜里，她上了车，后视镜里有人影。",
        }
        policy = default_audio_policy()
        r, _ = suggest_recipe_for_shot(
            shot, policy=policy, vo_mode="storyteller", index=0, n_shots=6, sung_slots_left=0
        )
        self.assertEqual(r, "narrate_bed")

    def test_sung_degrades_without_provider(self) -> None:
        shot = {
            "id": "s5",
            "dramatic_function": "action",
            "nar": "再近一点。",
            "camera": {"shot_size": "cu"},
            "audio_recipe": "sung_beat",
        }
        policy = validate_audio_policy({"mode": "musical_hybrid", "allow_sung": True})
        rec = resolve_shot_audio_recipe(
            shot,
            policy=policy,
            vo_mode="hybrid",
            index=4,
            n_shots=5,
            sung_slots_left=1,
            caps={
                "lipsync_ready": False,
                "music_library": False,
                "sung_provider_ready": False,
            },
        )
        self.assertEqual(rec["recipe"], "narrate_bed")
        self.assertEqual(rec["degraded_from"], "sung_beat")

    def test_apply_fills_shots(self) -> None:
        shots = [
            {
                "id": "shot01",
                "dramatic_function": "hook",
                "nar": "夜里她推门进来，外套还带着雨。",
            },
            {
                "id": "shot02",
                "dramatic_function": "sensory",
                "nar": "呼吸。",
                "camera": {"shot_size": "ecu"},
            },
            {
                "id": "shot03",
                "dramatic_function": "afterglow",
                "nar": "灯灭了。",
            },
        ]
        spec: dict = {
            "vo_mode": "storyteller",
            "sound_plan": {"mood": "rnb", "bed": True, "events": []},
        }
        summary = apply_audio_recipes_to_spec(spec, shots)
        self.assertTrue(summary["ok"])
        self.assertIn("audio_policy", spec)
        self.assertIn("_audio_routing", spec)
        self.assertEqual(shots[0]["audio_recipe"]["recipe"], "narrate_bed")
        self.assertEqual(shots[1]["audio_recipe"]["recipe"], "bed_focus")
        # storyteller forces lipsync false
        self.assertFalse(shots[0].get("lipsync"))
        self.assertGreater(summary["counts"]["narrate_bed"], 0)


if __name__ == "__main__":
    unittest.main()
