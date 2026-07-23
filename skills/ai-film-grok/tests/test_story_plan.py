#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from drama_graph import validate_graph  # noqa: E402
from story_plan import (  # noqa: E402
    export_legacy_story_plan,
    normalize_story,
    normalize_story_graph,
    project_graph_to_film_spec,
    run_plan,
)


class StoryPlanTests(unittest.TestCase):
    def test_one_liner_plan_meets_dod(self) -> None:
        """DoD: one-line idea → valid graph with ≥3 beats + film-spec seed."""
        idea = "雨夜出租车，女司机与乘客的距离越来越近，后视镜里呼吸先越线。"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = run_plan(
                root,
                idea,
                title="雨夜后座",
                target_duration=40,
                apply_film_spec=True,
                force=True,
            )
            self.assertTrue(report.get("ok"), report)
            counts = report.get("counts") or {}
            self.assertGreaterEqual(counts.get("beats") or 0, 3)
            self.assertGreaterEqual(counts.get("shots") or 0, 3)
            self.assertGreaterEqual(counts.get("episodes") or 0, 1)
            self.assertTrue((root / "drama-graph.json").is_file())
            self.assertTrue((root / "film-spec.json").is_file())
            self.assertTrue((root / "receipts" / "story-normalize.json").is_file())

            graph = json.loads((root / "drama-graph.json").read_text(encoding="utf-8"))
            self.assertEqual((graph.get("derived_from") or {}).get("mode"), "planned")
            v = validate_graph(graph)
            self.assertTrue(v.get("ok"), v)

            # every shot has beatId + panel
            shots = []
            for ep in graph["episodes"]:
                for sc in ep["scenes"]:
                    for bt in sc["beats"]:
                        for sh in bt["shots"]:
                            shots.append(sh)
                            self.assertTrue(sh.get("beatId"))
                            self.assertTrue(sh.get("panels"))
                            self.assertEqual(sh.get("verticalComposition") is not None, True)

            spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            self.assertEqual(spec.get("aspect_ratio"), "9:16")
            self.assertIn("director_intent", spec)
            self.assertGreaterEqual(len(spec["director_intent"].get("logline") or ""), 8)
            flat = []
            for sc in spec.get("scenes") or []:
                flat.extend(sc.get("shots") or [])
            self.assertGreaterEqual(len(flat), 3)
            for sh in flat:
                self.assertTrue(sh.get("id"))
                self.assertTrue(sh.get("nar"))
                self.assertTrue(sh.get("dramatic_function"))
                self.assertTrue(sh.get("dsl"))
                self.assertTrue(sh.get("beat_id"))

    def test_multi_scene_headers(self) -> None:
        raw = """# 旧电梯

## 场景：一楼大厅
她按下上行键，灯灭了一秒。

## 场景：电梯轿厢
门合上。他站在角落，呼吸很近。
"""
        norm = normalize_story(raw, title_hint="旧电梯")
        self.assertEqual(norm["title"], "旧电梯")
        self.assertGreaterEqual(len(norm.get("scene_chunks") or []), 2)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = run_plan(root, raw, target_duration=50, force=True)
            self.assertTrue(report.get("ok"), report)
            self.assertGreaterEqual((report.get("counts") or {}).get("scenes") or 0, 2)

    def test_force_required_when_shots_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "第一次规划一句话故事足够长。", force=True)
            report2 = run_plan(root, "第二次覆盖。", force=False)
            self.assertTrue(report2.get("ok"))  # graph still ok
            fs = report2.get("film_spec") or {}
            self.assertTrue(fs.get("skipped"))

    def test_project_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "地铁末班车，两个人沉默对视后突然开口。", force=True)
            graph = json.loads((root / "drama-graph.json").read_text(encoding="utf-8"))
            spec = project_graph_to_film_spec(graph)
            self.assertTrue(spec["scenes"][0]["shots"])

    def test_legacy_flat_graph_is_normalized_without_losing_ids(self) -> None:
        legacy = {
            "title": "旧格式",
            "scenes": [{
                "id": "scene-A",
                "beats": [{"id": "beat-A", "shots": [{"id": "shot-A"}]}],
            }],
        }
        graph = normalize_story_graph(legacy)
        self.assertEqual(graph["story_plan_schema_version"], 2)
        self.assertEqual(graph["episodes"][0]["id"], "ep01")
        self.assertEqual(graph["episodes"][0]["scenes"][0]["id"], "scene-A")
        self.assertEqual(graph["episodes"][0]["scenes"][0]["beats"][0]["id"], "beat-A")
        self.assertEqual(
            graph["episodes"][0]["scenes"][0]["beats"][0]["shots"][0]["id"], "shot-A"
        )
        self.assertNotIn("scenes", graph)

    def test_nested_multi_episode_roundtrip_to_explicit_legacy_shape(self) -> None:
        nested = {
            "episodes": [
                {"id": "ep01", "scenes": [{"id": "sc01", "beats": [{"id": "bt01", "shots": [{"id": "sh01"}]}]}]},
                {"id": "ep02", "scenes": [{"id": "sc02", "beats": [{"id": "bt02", "shots": [{"id": "sh02"}]}]}]},
            ]
        }
        legacy = export_legacy_story_plan(nested)
        self.assertEqual([shot["id"] for shot in legacy["shots"]], ["sh01", "sh02"])
        self.assertEqual([shot["episode_id"] for shot in legacy["shots"]], ["ep01", "ep02"])
        self.assertEqual(normalize_story_graph(legacy)["episodes"][0]["id"], "ep01")

    def test_empty_episode_is_safe_for_projection(self) -> None:
        graph = normalize_story_graph({"episodes": [{"id": "ep-empty", "scenes": []}]})
        self.assertEqual(graph["episodes"][0]["id"], "ep-empty")
        spec = project_graph_to_film_spec(graph)
        self.assertEqual(spec["scenes"], [])


if __name__ == "__main__":
    unittest.main()
