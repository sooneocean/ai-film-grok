#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cinema_prompt import (  # noqa: E402
    CAMERA_MOVES,
    DF_CAMERA_MAP,
    SCENARIO_STRATEGIES,
    CinemaPromptError,
    build_camera_prompt,
    inject_camera_prompts,
)
from util import read_json, write_json  # noqa: E402


class CinemaPromptTests(unittest.TestCase):
    def test_build_prompt_has_rich_text(self) -> None:
        """DoD: build_camera_prompt returns rich Chinese prose, not just an enum."""
        data = build_camera_prompt(dramatic_function="hook", shot_index=0, duration_sec=6.0)
        self.assertEqual(data["camera_axis"], "dolly_in")
        prompt = data["camera_prompt"]
        self.assertIn("推镜", prompt)
        self.assertIn("景", prompt)  # shot type (中近景/特写/远景 etc.)
        self.assertIn("布光", prompt)
        self.assertGreater(len(prompt), 30)

    def test_idx_modulation_matches_story_plan(self) -> None:
        """idx % 3 == 1 with dolly_in base → ecu_hold (backward-compat with story_plan)."""
        base = build_camera_prompt(dramatic_function="hook", shot_index=0)
        self.assertEqual(base["camera_axis"], "dolly_in")
        mod = build_camera_prompt(dramatic_function="hook", shot_index=1)
        self.assertEqual(mod["camera_axis"], "ecu_hold")

    def test_scenario_strategy_overrides(self) -> None:
        """scene_type strategy can override move/pacing/palette."""
        data = build_camera_prompt(
            dramatic_function="bridge",
            shot_index=0,
            scene_type="music_video",
        )
        # music_video strategy moves: handheld/orbit/tracking/dolly_in — not 'locked'
        self.assertIn(data["camera_move"], SCENARIO_STRATEGIES["music_video"]["moves"])
        self.assertEqual(data["pacing"], "fast")

    def test_heat_phase_modulation(self) -> None:
        """heat_phase modulates pacing + palette."""
        data = build_camera_prompt(dramatic_function="hook", shot_index=0, heat_phase="climax")
        self.assertEqual(data["pacing"], "hold")
        self.assertEqual(data["palette"], "high_contrast")

    def test_vocabulary_coverage(self) -> None:
        """Every dramatic_function maps to a known camera move."""
        for df in DF_CAMERA_MAP:
            move = build_camera_prompt(dramatic_function=df, shot_index=0)["camera_move"]
            self.assertIn(move, CAMERA_MOVES, f"df={df} → unknown move {move}")

    def test_inject_into_film_spec(self) -> None:
        """DoD: inject_camera_prompts writes dsl.camera_prompt to every shot."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = {
                "title": "t",
                "scenes": [
                    {
                        "id": "s1",
                        "shots": [
                            {
                                "id": "sh1",
                                "dsl": {"dramatic_function": "hook"},
                                "duration_sec": 5.0,
                            },
                            {
                                "id": "sh2",
                                "dsl": {"dramatic_function": "reaction"},
                                "duration_sec": 4.0,
                            },
                        ],
                    }
                ],
            }
            write_json(root / "film-spec.json", spec)
            report = inject_camera_prompts(root)
            self.assertTrue(report["ok"])
            self.assertEqual(report["shots_updated"], 2)
            updated = read_json(root / "film-spec.json")
            prompts = [
                s["dsl"].get("camera_prompt") for sc in updated["scenes"] for s in sc["shots"]
            ]
            self.assertTrue(all(p for p in prompts))

    def test_inject_idempotent(self) -> None:
        """Re-running produces the same camera_prompt (deterministic)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = {
                "title": "t",
                "scenes": [
                    {
                        "id": "s1",
                        "shots": [
                            {"id": "sh1", "dsl": {"dramatic_function": "hook"}, "duration_sec": 5.0}
                        ],
                    }
                ],
            }
            write_json(root / "film-spec.json", spec)
            inject_camera_prompts(root)
            from util import read_json

            first = read_json(root / "film-spec.json")
            inject_camera_prompts(root)
            second = read_json(root / "film-spec.json")
            self.assertEqual(
                first["scenes"][0]["shots"][0]["dsl"]["camera_prompt"],
                second["scenes"][0]["shots"][0]["dsl"]["camera_prompt"],
            )

    def test_inject_missing_spec_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CinemaPromptError):
                inject_camera_prompts(Path(tmp))


if __name__ == "__main__":
    unittest.main()
