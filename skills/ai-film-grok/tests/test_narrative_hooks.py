from __future__ import annotations

import json
from pathlib import Path

import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from narrative_control import validate_narrative_graph  # noqa: E402
from narrative_evidence import build_narrative_evidence, validate_narrative_evidence  # noqa: E402
from story_plan import build_planned_graph, normalize_story  # noqa: E402


def _authored(graph: dict) -> dict:
    graph["story"].update(
        {
            "premise": "钥匙指向一扇不能打开的门",
            "logline": "她找到钥匙，却发现门后有人先一步等她。",
            "protagonist_goal": "找到门后的真相",
            "opposition": "门后的未知者",
            "stakes": "开门会暴露她的秘密",
            "climax_choice": "她决定开门",
            "ending_hook": "门后的人叫出了她的名字",
            "emotional_arc": ["疑惑", "恐惧", "决心"],
        }
    )
    for ep in graph["episodes"]:
        for scene in ep["scenes"]:
            scene.update({"purpose": "逼近门后真相", "entry_state": "未知", "exit_state": "更接近门后", "conflict": "门与未知者阻挡"})
            for beat in scene["beats"]:
                beat.update(
                    {
                        "obstacle": "未知者阻挡",
                        "tactic": "追踪钥匙留下的线索",
                        "turn": "门后出现新反应",
                        "outcome": "线索继续推进",
                        "state_delta": "秘密更接近曝光",
                        "audience_question": "门后是谁？",
                        "emotional_turn": "疑惑转为恐惧",
                        "director_board": {
                            "emotional_turn": "疑惑转为恐惧",
                            "audience_question": "门后是谁？",
                            "image_priority": "钥匙与门缝",
                            "sound_priority": "门后的呼吸",
                            "coverage_strategy": "先道具再反应",
                            "cut_intent": "在门响时切",
                            "approval_state": "approved",
                        },
                    }
                )
                for shot in beat["shots"]:
                    shot.update(
                        {
                            "start_state": "疑惑",
                            "end_state": "更接近门后",
                            "playable_action": "她握紧钥匙并靠近门",
                            "expectation": "门后会出现回应",
                            "subtext": "她害怕秘密被认出",
                            "gaze_target": "门缝",
                            "reaction_trigger": "门后传来声音",
                            "body_state": "手指绷紧",
                        }
                    )
    return graph


def test_explicit_episode_headers_seed_cross_episode_contract() -> None:
    raw = "# 第1集\n她发现一把钥匙。\n\n# 第2集\n她用钥匙打开旧门。"
    graph = build_planned_graph(normalize_story(raw), target_duration=30)
    assert [ep["id"] for ep in graph["episodes"]] == ["ep01", "ep02"]
    assert graph["episodes"][0]["ending_hook"]["point_id"] in graph["episodes"][1]["carry_in_points"]
    assert graph["episodes"][0]["ending_hook"]["point_id"] in graph["episodes"][1]["payoff_points"]
    assert all(ep.get("opening_hook") and ep.get("mid_episode_points") and ep.get("ending_hook") for ep in graph["episodes"])
    assert all(any(str(sh["id"]).startswith(f"ep{i:02d}_") for sc in ep["scenes"] for bt in sc["beats"] for sh in bt["shots"]) for i, ep in enumerate(graph["episodes"], 1))


def test_strict_validation_rejects_missing_midpoint_point() -> None:
    graph = _authored(build_planned_graph(normalize_story("钥匙指向门后的秘密。"), target_duration=30))
    graph["episodes"][0]["mid_episode_points"] = []
    report = validate_narrative_graph(graph, strict=True)
    assert "EPISODE_MIDPOINT_POINT_MISSING" in report["issue_codes"]


def test_narrative_evidence_requires_executed_and_human_readback(tmp_path: Path) -> None:
    graph = _authored(build_planned_graph(normalize_story("钥匙指向门后的秘密。"), target_duration=30))
    (tmp_path / "drama-graph.json").write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    build_narrative_evidence(tmp_path)
    missing = validate_narrative_evidence(tmp_path)
    assert not missing["ok"]
    evidence = json.loads((tmp_path / "narrative-evidence.json").read_text(encoding="utf-8"))
    for item in evidence["items"]:
        item["evidence_status"] = "verified"
        item["executed"] = {"shot_ids": item["shot_ids"], "time_range": [0.0, 1.0]}
        item["human_review"] = {"approved": True, "reviewer": "user"}
    (tmp_path / "narrative-evidence.json").write_text(json.dumps(evidence, ensure_ascii=False), encoding="utf-8")
    assert validate_narrative_evidence(tmp_path)["ok"]
