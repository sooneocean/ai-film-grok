from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dispatch import build_dispatch  # noqa: E402
from narrative_control import (  # noqa: E402
    NarrativeControlError,
    edit_node,
    graph_content_sha256,
    graph_locked_for_projection,
    lock_scope,
    mark_replan,
    projection_status,
    validate_narrative_graph,
)
from story_plan import run_plan, stabilize_shot_ids  # noqa: E402


def _fill_graph(graph: dict) -> dict:
    graph["story"].update(
        {
            "premise": "雨夜出租車中的秘密相遇",
            "logline": "末班乘客拿著照片逼近女司機的秘密。",
            "protagonist_goal": "女司機想保住秘密",
            "opposition": "乘客用照片逼她面對過去",
            "stakes": "秘密曝光就失去工作與安全",
            "climax_choice": "她選擇停車並承認真相",
            "ending_hook": "照片背面還有下一個地址",
            "emotional_arc": ["戒備", "逼近", "承認"],
        }
    )
    for ep in graph.get("episodes") or []:
        for scene in ep.get("scenes") or []:
            scene.update(
                {
                    "purpose": "逼近秘密",
                    "conflict": "司機拒絕回答",
                    "entry_state": "戒備",
                    "exit_state": "秘密被承認",
                }
            )
            for beat in scene.get("beats") or []:
                beat.update(
                    {
                        "objective": "推進關係",
                        "obstacle": "對方拒絕回應",
                        "tactic": "用線索逼近",
                        "turn": "新線索改變局面",
                        "outcome": "關係向前一步",
                        "state_delta": "秘密更接近曝光",
                        "audience_question": "她会不会说出真相",
                        "emotional_turn": "防卫转为坦白",
                        "director_board": {
                            "emotional_turn": "防卫转为坦白",
                            "audience_question": "她会不会说出真相",
                            "image_priority": "后视镜里的眼神",
                            "sound_priority": "雨声压住沉默",
                            "coverage_strategy": "反应后给线索特写",
                            "cut_intent": "在呼吸停顿处切",
                            "approval_state": "approved",
                        },
                    }
                )
                for shot in beat.get("shots") or []:
                    shot.update(
                        {
                            "beat_id": beat["id"],
                            "coverage_role": shot.get("coverage_role") or "reveal",
                            "must_show": shot.get("must_show") or "揭示線索",
                            "visible_change": shot.get("visible_change") or "新線索出現",
                            "start_state": "戒備",
                            "end_state": "更接近真相",
                            "playable_action": "她把照片翻到背面",
                            "expectation": "她以为背面没有内容",
                            "subtext": "她害怕被认出来",
                            "gaze_target": "照片背面",
                            "reaction_trigger": "看见地址",
                            "body_state": "手指停住，肩膀绷紧",
                        }
                    )
    for point in graph.get("plot_points") or []:
        point.update(
            {
                "source_excerpt": "雨夜出租車，兩人的距離越來越近。",
                "visible_evidence": "照片背面出现地址",
                "authoring_status": "confirmed",
                "confidence": 1.0,
            }
        )
    for ep in graph.get("episodes") or []:
        for hook_name in ("opening_hook", "ending_hook"):
            hook = ep.get(hook_name)
            if isinstance(hook, dict):
                hook.update(
                    {
                        "source_refs": ["test:authored-source"],
                        "visible_evidence": "照片背面出现地址",
                    }
                )
        arc = ep.get("narrative_arc") or {}
        (arc.get("reversal") or {}).update(
            {
                "setup_expectation": "她以为照片背面没有内容",
                "revealed_truth": "背面有能改变局面的地址",
                "visible_consequence": "她停住动作并决定面对过去",
            }
        )
        (arc.get("payoff") or {}).update(
            {
                "resolves_point_ids": [str(x) for x in ep.get("carry_in_points") or []],
                "visible_change": "她用行动回应了已知线索",
            }
        )
    (graph.get("story_resolution") or {}).update(
        {
            "climax_choice": "她选择停車并承认真相",
            "outcome": "她不再逃避照片揭示的过去",
            "final_state": "她带着新的地址继续前行",
        }
    )
    return graph


@pytest.mark.slow
class NarrativeControlTests(unittest.TestCase):
    @pytest.mark.slow
    def test_plan_is_draft_and_semantic_errors_are_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = run_plan(root, "雨夜出租車，兩人的距離越來越近。", apply_film_spec=False)
            self.assertTrue(report["ok"])
            self.assertTrue(report["draft"])
            self.assertFalse(report["ready_for_projection"])
            graph = json.loads((root / "drama-graph.json").read_text(encoding="utf-8"))
            self.assertEqual(graph["schema_version"], 2)
            self.assertIn("STORY_GOAL_MISSING", report["narrative"]["issue_codes"])
            shots = [
                sh
                for ep in graph["episodes"]
                for sc in ep["scenes"]
                for bt in sc["beats"]
                for sh in bt["shots"]
            ]
            self.assertTrue(all(sh["id"].startswith("ep01_sc") for sh in shots))
            self.assertGreater(len({sh["must_show"] for sh in shots}), 1)

    @pytest.mark.slow
    def test_edit_stales_descendants_and_locked_scope_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "雨夜出租車，兩人的距離越來越近。", apply_film_spec=False)
            graph = json.loads((root / "drama-graph.json").read_text(encoding="utf-8"))
            graph = _fill_graph(graph)
            graph, affected = edit_node(graph, "story", {"theme": "秘密與選擇"})
            self.assertTrue(affected)
            self.assertTrue(
                all(
                    item["control"]["state"] == "stale"
                    for ep in graph["episodes"]
                    for sc in ep["scenes"]
                    for bt in sc["beats"]
                    for item in bt["shots"]
                )
            )
            lock_scope(graph, "story", user_phrase="使用者確認故事")
            with self.assertRaises(NarrativeControlError) as ctx:
                edit_node(graph, "story", {"theme": "不可靜默改寫"})
            self.assertEqual(ctx.exception.code, "LOCKED_NODE_MUTATION")

    @pytest.mark.slow
    def test_full_lock_and_projection_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "雨夜出租車，兩人的距離越來越近。", apply_film_spec=False)
            graph = json.loads((root / "drama-graph.json").read_text(encoding="utf-8"))
            graph = _fill_graph(graph)
            lock_scope(graph, "story", user_phrase="故事確認")
            lock_scope(graph, "beats", user_phrase="Beat 確認")
            lock_scope(graph, "shots", user_phrase="分鏡確認")
            lock_scope(graph, "panels", user_phrase="Panel 確認")
            ready = graph_locked_for_projection(graph)
            self.assertTrue(ready["ok"], ready)
            self.assertEqual(len(graph_content_sha256(graph)), 64)
            (root / "drama-graph.json").write_text(
                json.dumps(graph, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            # No spec means not yet projected, but the graph itself is ready.
            self.assertTrue(validate_narrative_graph(graph)["ok"])
            self.assertFalse(projection_status(root, graph)["ok"])

    @pytest.mark.slow
    def test_replan_marks_subtree_without_deleting_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "雨夜出租車，兩人的距離越來越近。", apply_film_spec=False)
            graph = json.loads((root / "drama-graph.json").read_text(encoding="utf-8"))
            beat_id = graph["episodes"][0]["scenes"][0]["beats"][2]["id"]
            affected = mark_replan(graph, beat_id)
            self.assertIn(beat_id, affected)
            beat = graph["episodes"][0]["scenes"][0]["beats"][2]
            self.assertEqual(beat["control"]["state"], "stale")
            self.assertTrue(all(sh["control"]["state"] == "stale" for sh in beat["shots"]))

    @pytest.mark.slow
    def test_dispatch_stops_at_narrative_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "雨夜出租車，兩人的距離越來越近。", apply_film_spec=False)
            packet = build_dispatch(root, include_capability=False, write_receipt=False)
            self.assertEqual(packet.get("next_id"), "narrative-validate")
            self.assertFalse((packet.get("narrative_control") or {}).get("ready_for_media"))

    @pytest.mark.slow
    def test_stabilize_ids_reuses_existing_semantic_slots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "雨夜出租車，兩人的距離越來越近。", apply_film_spec=False)
            old = json.loads((root / "drama-graph.json").read_text(encoding="utf-8"))
            new = json.loads(json.dumps(old))
            beat = new["episodes"][0]["scenes"][0]["beats"][0]
            extra = json.loads(json.dumps(beat["shots"][0]))
            extra["coverage_role"] = "consequence"
            extra["id"] = "ep01_sc01_bt01_sh99"
            beat["shots"].insert(0, extra)
            stabilized = stabilize_shot_ids(new, old)
            ids = [sh["id"] for sh in stabilized["episodes"][0]["scenes"][0]["beats"][0]["shots"]]
            old_ids = [sh["id"] for sh in old["episodes"][0]["scenes"][0]["beats"][0]["shots"]]
            self.assertIn(old_ids[0], ids)

    @pytest.mark.slow
    def test_plan_validate_cli_emits_json_after_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "一句話草稿。", apply_film_spec=False)
            proc = subprocess.run(
                [str(SCRIPTS / "aifilm"), "plan", "validate", "--root", str(root), "--strict"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertFalse(report["ok"])
            self.assertIn("STORY_GOAL_MISSING", report["issue_codes"])

    @pytest.mark.slow
    def test_projection_hash_drift_is_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "雨夜出租車，兩人的距離越來越近。", apply_film_spec=False)
            graph = json.loads((root / "drama-graph.json").read_text(encoding="utf-8"))
            graph = _fill_graph(graph)
            source_hash = graph_content_sha256(graph)
            (root / "film-spec.json").write_text(
                json.dumps(
                    {"_projection": {"source": "drama-graph.json", "source_sha256": source_hash}},
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertTrue(projection_status(root, graph)["ok"])
            graph["story"]["theme"] = "被编辑后的主题"
            self.assertTrue(projection_status(root, graph)["stale"])

    @pytest.mark.slow
    def test_beat_lock_requires_an_approved_director_board(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_plan(root, "雨夜出租車，兩人的距離越來越近。", apply_film_spec=False)
            graph = _fill_graph(json.loads((root / "drama-graph.json").read_text(encoding="utf-8")))
            for ep in graph["episodes"]:
                for scene in ep["scenes"]:
                    for beat in scene["beats"]:
                        beat["director_board"]["approval_state"] = "review"
            with self.assertRaises(NarrativeControlError) as ctx:
                lock_scope(graph, "beats", user_phrase="先锁节拍")
            self.assertEqual(ctx.exception.code, "NARRATIVE_NOT_VALID")
            for ep in graph["episodes"]:
                for scene in ep["scenes"]:
                    for beat in scene["beats"]:
                        beat["director_board"]["approval_state"] = "approved"
            lock_scope(graph, "beats", user_phrase="导演确认节拍")


if __name__ == "__main__":
    unittest.main()
