#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from edit_strategy import (  # noqa: E402
    apply_edit_strategy_to_spec,
    plan_join_transition_secs,
    resolve_edit_strategy,
)


class EditStrategyTest(unittest.TestCase):
    def test_auto_mode_max_heat(self) -> None:
        s = resolve_edit_strategy({"heat_scale": "max", "edit_strategy": {"mode": "auto"}})
        self.assertEqual(s["mode"], "voice_coupled")

    def test_join_secs_vary(self) -> None:
        strat = resolve_edit_strategy({"edit_strategy": {"mode": "voice_coupled"}})
        secs = plan_join_transition_secs(
            ["smash_cut", "soft_glue", "mood_hold", "montage_jump"],
            strategy=strat,
        )
        self.assertEqual(len(secs), 4)
        self.assertLess(secs[0], secs[1])  # hard micro < soft
        self.assertGreater(secs[2], secs[1])  # hold longest

    def test_apply_sets_vo_fit_and_crafts(self) -> None:
        spec = {
            "heat_scale": "max",
            "edit_strategy": {"mode": "voice_coupled", "lock_craft": False},
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "shot01",
                            "dramatic_function": "hook",
                            "heat_phase": "setup",
                            "duration_sec": 6,
                            "dsl": {"chain_mode": "hard"},
                        },
                        {
                            "id": "shot02",
                            "dramatic_function": "action",
                            "heat_phase": "act",
                            "duration_sec": 6,
                            "vocal_color": "啊…嗯…",
                            "tone_tags": ["moan"],
                            "sound_cues": ["impact"],
                            "dsl": {},
                        },
                        {
                            "id": "shot03",
                            "dramatic_function": "action",
                            "heat_phase": "climax",
                            "duration_sec": 6,
                            "vocal_color": "啊——",
                            "dsl": {},
                        },
                        {
                            "id": "shot04",
                            "dramatic_function": "afterglow",
                            "heat_phase": "afterglow",
                            "duration_sec": 6,
                            "vocal_color": "呼…",
                            "tone_tags": ["afterglow"],
                            "dsl": {},
                        },
                    ]
                }
            ],
        }
        plan = apply_edit_strategy_to_spec(spec)
        self.assertTrue(plan["ok"])
        self.assertGreaterEqual(plan["n_unique_crafts"], 2)
        self.assertEqual(len(spec["edit_craft"]), 3)
        self.assertEqual(len(spec["join_transition_secs"]), 3)
        # act/climax vo fit
        shots = spec["scenes"][0]["shots"]
        self.assertEqual(shots[1].get("visual_fit"), "vo")
        self.assertEqual(shots[2].get("visual_fit"), "vo")
        # afterglow has color offset
        self.assertIsNotNone(shots[3].get("vocal_color_offset_sec"))


if __name__ == "__main__":
    unittest.main()
