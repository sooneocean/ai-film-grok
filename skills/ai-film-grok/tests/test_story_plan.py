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
from film_spec import FilmSpecError, validate_film_spec  # noqa: E402
from narrative_control import validate_narrative_graph  # noqa: E402
from story_plan import (  # noqa: E402
    build_planned_graph,
    export_legacy_story_plan,
    normalize_story,
    normalize_story_graph,
    project_graph_to_film_spec,
    run_plan,
)
from util import FilmError  # noqa: E402


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
                self.assertFalse(sh.get("nar"))
                self.assertTrue(sh.get("audio_cues"))
                self.assertTrue(sh.get("dramatic_function"))
                self.assertTrue(sh.get("dsl"))
                self.assertTrue(sh.get("beat_id"))
            self.assertEqual(spec["vo_mode"], "dialogue_drama")
            self.assertEqual(graph["dialogue_screenplay"]["status"], "candidate_only")

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

    def test_metadata_only_sections_never_become_scenes(self) -> None:
        raw = """【角色表】
女主：阿澄

【00:00-00:05】
阿澄推开雨中的车门，回头看见他还站在路灯下。

【格式说明】
竖屏，中文字幕。
"""
        norm = normalize_story(raw, title_hint="雨夜")
        chunks = norm["scene_chunks"]
        self.assertEqual(len(chunks), 1)
        self.assertIn("推开雨中的车门", chunks[0]["body"])

    def test_metadata_synonyms_never_become_scenes(self) -> None:
        for label in ("角色设定", "人物设定", "制作备注"):
            raw = f"""【{label}】
这是元数据。

【00:00-00:05】
她收起伞，走进空无一人的车站。
"""
            chunks = normalize_story(raw, title_hint="车站")["scene_chunks"]
            self.assertEqual(len(chunks), 1, label)
            self.assertIn("收起伞", chunks[0]["body"])

    def test_project_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "地铁末班车，两个人沉默对视后突然开口。", force=True)
            graph = json.loads((root / "drama-graph.json").read_text(encoding="utf-8"))
            spec = project_graph_to_film_spec(graph)
            self.assertTrue(spec["scenes"][0]["shots"])

    def test_named_dialogue_projects_to_dialogue_drama_without_default_narration(self) -> None:
        raw = """阿澄：你为什么还没下车？
乘客：因为照片背后写着你的名字。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = run_plan(root, raw, title="末班车", target_duration=24, force=True)
            self.assertTrue(report["ok"], report)
            graph = json.loads((root / "drama-graph.json").read_text(encoding="utf-8"))
            self.assertEqual(len(graph.get("dialogue_ledger") or []), 2)
            strict_graph = validate_narrative_graph(graph, strict=True)
            self.assertFalse(strict_graph["ok"])
            self.assertIn(
                "STORY_DIALOGUE_SCREENPLAY_REVIEW_REQUIRED",
                {item["code"] for item in strict_graph["errors"]},
            )
            spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            self.assertEqual(spec["vo_mode"], "dialogue_drama")
            shots = [shot for scene in spec["scenes"] for shot in scene["shots"]]
            speaking = [shot for shot in shots if shot.get("screen_mode") == "on_camera"]
            self.assertEqual(len(speaking), 2)
            self.assertTrue(all(not shot.get("nar") for shot in shots))
            self.assertTrue(all(shot["audio_cues"] for shot in shots))
            self.assertTrue(all(shot["lipsync_required"] is True for shot in speaking))
            self.assertTrue(all(shot["lipsync"] is True for shot in speaking))
            self.assertTrue(all(shot["translation_status"] == "pending" for shot in speaking))
            self.assertTrue(all(shot["dialogue_motion_route"] == "auto" for shot in speaking))
            self.assertTrue(
                all(
                    shot["dsl"]["camera"]["shot_size"]
                    in {"close-up", "ecu", "extreme close-up", "medium close-up"}
                    for shot in speaking
                )
            )
            coverage = [shot for shot in shots if shot.get("screen_mode") == "action_cover"]
            self.assertTrue(any(shot["dsl"]["camera"]["shot_size"] == "wide" for shot in coverage))
            covered_beats = {
                shot.get("beat_id")
                for shot in shots
                if shot.get("screen_mode") in {"reaction", "action_cover", "silence"}
            }
            self.assertTrue(
                all(
                    (shot.get("beat_id") or shot.get("dialogue_line_id") or shot.get("id"))
                    in covered_beats
                    for shot in speaking
                )
            )
            for index, shot in enumerate(shots):
                if not shot.get("auto_dialogue_coverage"):
                    continue
                self.assertGreater(index, 0)
                previous = shots[index - 1]
                self.assertEqual(previous.get("screen_mode"), "on_camera")
                self.assertEqual(previous.get("beat_id"), shot.get("beat_id"))
            for shot, japanese in zip(
                speaking, ("まだ降りないの？", "写真の裏に君の名前がある。"), strict=True
            ):
                shot["dialogue_ja"] = japanese
                shot["dialogue"] = japanese
                shot["translation_status"] = "ready"
                shot["audio_cues"][0]["spoken_text"] = japanese
                shot["audio_cues"][0]["translation_status"] = "ready"
            # This dialogue-only fixture is not an adult-max heat arc; keep the
            # coverage assertion isolated from the unrelated adult IRON gate.
            spec["heat_arc_strict"] = False
            spec["adult_max_iron"] = False
            validate_film_spec(spec, assign_missing_ids=False)
            self.assertGreater((spec.get("_dialogue_drama") or {}).get("coverage_shots", 0), 0)
            missing_beat = speaking[0].get("beat_id") or speaking[0].get("dialogue_line_id")
            for scene in spec["scenes"]:
                scene["shots"] = [
                    shot
                    for shot in scene["shots"]
                    if not (
                        shot.get("screen_mode") in {"reaction", "action_cover", "silence"}
                        and shot.get("beat_id") == missing_beat
                    )
                ]
            with self.assertRaisesRegex(FilmSpecError, "every dialogue beat"):
                validate_film_spec(spec, assign_missing_ids=False)
            self.assertEqual(
                speaking[0]["_recommended_engine"]["motion_primary"],
                "frw_ltx23_img2video_audio",
            )
            self.assertEqual(
                speaking[0]["_recommended_engine"]["lipsync_primary"],
                "frw_ltx23_native_audio_i2v_human_verified",
            )
            self.assertEqual(
                speaking[0]["_recommended_engine"]["lipsync_fallback"],
                "rtx_latentsync_1_6_after_frw_img2video_fallback",
            )
            self.assertEqual(
                speaking[0]["_recommended_engine"]["motion_fallback"],
                "frw_img2video_rejection_only",
            )
            self.assertEqual(speaking[0]["audio_recipe"]["recipe"], "dialogue_lipsync")
            self.assertTrue(speaking[0]["audio_recipe"]["lipsync"])

    def test_dialogue_projection_never_collapses_extra_lines_onto_one_shot(self) -> None:
        raw = "\n".join(f"阿澄：第{i}句。" for i in range(1, 13))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, raw, title="十二句", target_duration=24, force=True)
            graph = json.loads((root / "drama-graph.json").read_text(encoding="utf-8"))
            ledger = graph.get("dialogue_ledger") or []
            self.assertEqual(len(ledger), 12)
            self.assertEqual(len({line["shot_ref"] for line in ledger}), 12)
            spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            speaking = [
                shot
                for scene in spec["scenes"]
                for shot in scene["shots"]
                if shot.get("screen_mode") == "on_camera"
            ]
            self.assertEqual(len(speaking), 12)

    def test_chinese_dialogue_blocks_tts_until_japanese_script_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "阿澄：别回头。", title="停", target_duration=12, force=True)
            spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            with self.assertRaisesRegex(Exception, "translation is pending"):
                validate_film_spec(spec, assign_missing_ids=False)

    def test_prose_adaptation_stays_candidate_until_translation_and_review(self) -> None:
        raw = (
            "阿澄推开车门，雨水打湿她的袖口。"
            "她看见后视镜里的乘客没有下车。"
            "乘客把落在座椅上的旧照片递给她。"
            "阿澄认出照片背面是自己失踪多年的姐姐。"
            "她把伞递过去，车门在两人之间轻轻合上。"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_plan(root, raw, title="雨夜车门", target_duration=45, force=True)
            self.assertTrue(result["ok"], result)
            spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            with self.assertRaisesRegex(Exception, "translation is pending"):
                validate_film_spec(spec, assign_missing_ids=False, film_root=root)
            graph = json.loads((root / "drama-graph.json").read_text(encoding="utf-8"))
            screenplay = graph["dialogue_screenplay"]
            self.assertEqual(screenplay["mode"], "dialogue_drama")
            self.assertEqual(screenplay["status"], "candidate_only")
            self.assertTrue(screenplay["scenes"][0]["dialogue_turns"])
            self.assertEqual(screenplay["narration_gaps"], [])

    def test_legacy_flat_graph_is_normalized_without_losing_ids(self) -> None:
        legacy = {
            "title": "旧格式",
            "scenes": [
                {
                    "id": "scene-A",
                    "beats": [{"id": "beat-A", "shots": [{"id": "shot-A"}]}],
                }
            ],
        }
        graph = normalize_story_graph(legacy)
        self.assertEqual(graph["story_plan_schema_version"], 2)
        self.assertEqual(graph["episodes"][0]["id"], "ep01")
        self.assertEqual(graph["episodes"][0]["scenes"][0]["id"], "scene-A")
        self.assertEqual(graph["episodes"][0]["scenes"][0]["beats"][0]["id"], "beat-A")
        self.assertEqual(graph["episodes"][0]["scenes"][0]["beats"][0]["shots"][0]["id"], "shot-A")
        self.assertNotIn("scenes", graph)

    def test_nested_multi_episode_roundtrip_to_explicit_legacy_shape(self) -> None:
        nested = {
            "episodes": [
                {
                    "id": "ep01",
                    "scenes": [
                        {"id": "sc01", "beats": [{"id": "bt01", "shots": [{"id": "sh01"}]}]}
                    ],
                },
                {
                    "id": "ep02",
                    "scenes": [
                        {"id": "sc02", "beats": [{"id": "bt02", "shots": [{"id": "sh02"}]}]}
                    ],
                },
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

    def test_pre_plan_validation_blocks_invalid_graph(self) -> None:
        """run_plan() raises FilmError when build_planned_graph returns
        a graph missing required top-level keys (e.g. story_resolution)."""
        from unittest.mock import patch

        raw = "雨夜出租车里的一次对话。"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def _return_invalid_graph(*args, **kwargs):
                graph = build_planned_graph(*args, **kwargs)
                del graph["story_resolution"]
                return graph

            with patch("story_plan.build_planned_graph", _return_invalid_graph):
                with self.assertRaises(FilmError) as cm:
                    run_plan(
                        root,
                        raw,
                        title="pre-plan-validation-test",
                        target_duration=30,
                        apply_film_spec=True,
                        force=True,
                    )
            self.assertIn("PRE_PLAN_NARRATIVE", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
