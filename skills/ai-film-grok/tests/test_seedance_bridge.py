#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cinema_prompt import inject_camera_prompts  # noqa: E402
from seedance_bridge import (  # noqa: E402
    DEFAULT_NEGATIVES,
    SeedanceBridgeError,
    bridge_film_spec,
    bridge_shot,
    build_seedance_prompt,
)
from story_plan import run_plan  # noqa: E402


class SeedanceBridgeTests(unittest.TestCase):
    def test_build_prompt_has_image_marker_and_camera(self) -> None:
        """DoD: prompt composes @Image1 + subject + action + camera_prompt."""
        result = build_seedance_prompt(
            subject="女主角近景",
            action="回眸呼吸",
            camera_prompt="缓慢推镜，大特写凝住。",
            scene_type="short_drama",
            duration_sec=5.0,
        )
        self.assertIn("@Image1", result["prompt"])
        self.assertIn("动作：", result["prompt"])
        self.assertIn("推镜", result["prompt"])
        self.assertEqual(result["segments"], [])  # ≤15s → no segments

    def test_multi_segment_for_long_clips(self) -> None:
        """>15s clips get timestamp storyboarding segments."""
        result = build_seedance_prompt(
            subject="s", action="a", camera_prompt="c", duration_sec=25.0
        )
        self.assertGreaterEqual(len(result["segments"]), 2)
        self.assertTrue(result["segments"][0]["time"])

    def test_negative_defaults_by_scene_type(self) -> None:
        for st in DEFAULT_NEGATIVES:
            result = build_seedance_prompt(subject="s", scene_type=st, duration_sec=5)
            self.assertTrue(result["negative"])

    def test_custom_negative_override(self) -> None:
        result = build_seedance_prompt(subject="s", duration_sec=5, negative="custom neg")
        self.assertEqual(result["negative"], "custom neg")

    def test_bridge_shot(self) -> None:
        shot = {
            "id": "sh1",
            "dsl": {"subject": "hero", "action": "walks", "camera_prompt": "dolly_in"},
            "duration_sec": 5.0,
        }
        result = bridge_shot(shot, scene_type="ecommerce")
        self.assertIn("@Image1", result["prompt"])

    def test_bridge_empty_raises(self) -> None:
        with self.assertRaises(SeedanceBridgeError):
            build_seedance_prompt()

    def test_end_to_end_story_plan_to_seedance(self) -> None:
        """DoD: story_plan → cinema_prompt inject → seedance bridge produces @Image1 prompt."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(
                root,
                "雨夜出租车",
                title="t",
                target_duration=40,
                apply_film_spec=True,
                force=True,
            )
            # inject cinema-grade camera_prompt
            inject_report = inject_camera_prompts(root)
            self.assertTrue(inject_report["ok"])
            # bridge to Seedance structured prompts
            bridge_report = bridge_film_spec(root)
            self.assertTrue(bridge_report["ok"])
            self.assertGreater(bridge_report["shots_bridged"], 0)
            first = bridge_report["shots"][0]
            self.assertIn("@Image1", first["prompt"])
            self.assertTrue(first["negative"])

    def test_bridge_missing_spec_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SeedanceBridgeError):
                bridge_film_spec(Path(tmp))


if __name__ == "__main__":
    unittest.main()
