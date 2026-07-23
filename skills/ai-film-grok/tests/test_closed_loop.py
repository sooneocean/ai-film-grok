#!/usr/bin/env python3
"""Closed-loop integration test: script → motion prompt → cut → render-advisory.

Exercises the full four-tool closed loop in-process (no network, no ffmpeg):
  story_plan → cinema_prompt inject → seedance_bridge → i2v_provider registry
  → color_grade plan → merge_edls (generated + simulated real-footage EDL)
  → duration_advisory

This proves the ai-film-grok × {HyperFrames, Remotion, video-use, Seedance}
closed loop composes end-to-end without raising.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cinema_prompt import inject_camera_prompts  # noqa: E402
from color_grade import plan_shot_grades  # noqa: E402
from compose_render import duration_advisory  # noqa: E402
from edit_policy import merge_edls  # noqa: E402
from i2v_provider import preferred, registry_report  # noqa: E402
from seedance_bridge import bridge_film_spec  # noqa: E402
from story_plan import run_plan  # noqa: E402
from util import read_json  # noqa: E402


class ClosedLoopTests(unittest.TestCase):
    def test_full_closed_loop(self) -> None:
        """DoD: script → motion prompt → cut → render-advisory, no exceptions.

        Walks the four-tool closed loop in one process:
          Seedance (cinema_prompt + seedance_bridge)  → motion prompts
          video-use (auto_cut EDL shape + merge_edls) → editing
          HyperFrames/Remotion (duration_advisory)   → render advisory
          i2v_provider (registry)                     → provider routing
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            # 1. Script/story planning (story_plan)
            plan_report = run_plan(
                root,
                "雨夜出租车，女司机与乘客的距离越来越近",
                title="雨夜后座",
                target_duration=45,
                apply_film_spec=True,
                force=True,
            )
            self.assertTrue(plan_report.get("ok"), plan_report)
            self.assertTrue((root / "film-spec.json").is_file())

            # 2. Seedance cinema-grade camera prompts (cinema_prompt)
            cinema_report = inject_camera_prompts(root)
            self.assertTrue(cinema_report["ok"])
            self.assertGreater(cinema_report["shots_updated"], 0)

            # 3. Seedance prompt bridge (seedance_bridge)
            bridge_report = bridge_film_spec(root)
            self.assertTrue(bridge_report["ok"])
            self.assertEqual(bridge_report["shots_bridged"], cinema_report["shots_updated"])
            # Every bridged prompt has @Image1 marker for I2V
            for shot in bridge_report["shots"]:
                self.assertIn("@Image1", shot["prompt"])
                self.assertTrue(shot["negative"])

            # 4. I2V provider registry (active provider resolvable)
            active = preferred(root=root)
            self.assertIsNotNone(active)
            reg = registry_report(root=root)
            self.assertIn("grok", reg["registered"])
            self.assertIn("seedance", reg["registered"])

            # 5. Color grade plan (cinema_prompt palette → ASC CDL)
            grade_report = plan_shot_grades(root)
            self.assertTrue(grade_report["ok"])
            self.assertGreater(len(grade_report["shots"]), 0)

            # 6. video-use editing: simulate a real-footage EDL + merge
            spec = read_json(root / "film-spec.json")
            generated_edl = {
                "version": 1,
                "sources": {
                    f"sh{i}": f"/clips/sh{i}.mp4"
                    for s in spec["scenes"]
                    for i, _ in enumerate(s.get("shots", []))
                },
                "ranges": [
                    {
                        "source": f"sh{i}",
                        "start": 0.0,
                        "end": float(sh.get("duration_sec", 5)),
                        "beat": "generated",
                    }
                    for s in spec["scenes"]
                    for i, sh in enumerate(s.get("shots", []))
                ],
                "grade": "none",
                "overlays": [],
                "subtitles": "/subs/master.srt",
                "source_type": "generated",
            }
            real_edl = {
                "version": 1,
                "sources": {"src1": "/footage/raw/src1.mp4"},
                "ranges": [
                    {"source": "src1", "start": 0.0, "end": 4.0, "beat": "real_seg1"},
                ],
                "grade": "warm_cinematic",
                "overlays": [],
                "subtitles": "/footage/edit/master.srt",
                "source_type": "real_footage",
            }
            merged = merge_edls(generated_edl, real_edl)
            self.assertTrue(merged["merged"])
            self.assertGreater(merged["segment_count"], 1)
            self.assertTrue(merged["hard_rules"]["subtitles_last"])

            # 7. HyperFrames/Remotion render advisory (duration policy)
            advisory = duration_advisory(merged["total_duration_s"])
            self.assertIn("segment_count", advisory)

            # 8. film-spec carries camera_prompt end-to-end
            spec_final = read_json(root / "film-spec.json")
            prompts = [
                s["dsl"].get("camera_prompt")
                for sc in spec_final["scenes"]
                for s in sc["shots"]
                if isinstance(s.get("dsl"), dict)
            ]
            self.assertTrue(all(p for p in prompts), "every shot must have camera_prompt")


if __name__ == "__main__":
    unittest.main()
