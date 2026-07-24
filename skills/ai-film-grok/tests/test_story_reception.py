"""Story reception contract and planning integration tests."""

from __future__ import annotations

import hashlib
import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from aifilm_grok import cmd_plan  # noqa: E402
from cli_plan_run import run as run_plan_cli  # noqa: E402
from story_reception import ReceptionError, load_story_reception  # noqa: E402


def reception(raw: str = "成年男女在雨夜重逢，彼此确认心意后走进公寓。") -> dict:
    return {
        "schema_version": 1,
        "kind": "story-reception",
        "source": {
            "raw_text": raw,
            "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            "language": "zh-CN",
            "source_ref": "user:story",
        },
        "fidelity": {
            "immutable_facts": ["两人是成年人", "在雨夜重逢"],
            "protected_dialogue": [],
            "explicit_constraints": ["角色关系必须自愿"],
            "unknowns": ["两人分开多年的原因"],
        },
        "treatment": {
            "title": "雨夜重逢",
            "logline": "两名成年人在雨夜重逢，在确认彼此意愿后面对未说出口的遗憾。",
            "theme": "亲密来自坦诚选择。",
            "protagonist_goal": "重新建立信任",
            "opposition": "旧日误解和不敢说出口的歉意",
            "stakes": "再次错过将失去修复关系的机会",
            "climax_choice": "主动说出当年离开的原因",
            "ending_hook": "门铃再次响起，答案尚未说完。",
            "emotional_arc": ["克制", "靠近", "坦诚", "余韵"],
            "act_structure": {
                "setup": "雨夜重逢",
                "confrontation": "旧误解浮现",
                "resolution": "确认意愿后坦诚相对",
                "setup_ratio": 0.2,
                "confrontation_ratio": 0.5,
                "resolution_ratio": 0.3,
            },
            "pace_chart": [
                {
                    "label": "靠近",
                    "start_ratio": 0,
                    "end_ratio": 1,
                    "cut_freq": "medium",
                    "intensity": 6,
                }
            ],
            "visual_motifs": ["雨水", "门锁"],
            "scene_beats": ["重逢", "确认意愿", "坦诚"],
            "sound_intent": "雨声与克制的呼吸声推进亲密张力。",
            "camera_intent": "由中景逐步收紧到保留头部空间的近景。",
            "planning_text": "# 雨夜重逢\n\n## 场景：公寓门口\n两名成年人确认彼此意愿后进入室内，雨声压住未说出口的话。\n\n## 场景：客厅\n他们面对旧日误解，最终主动说出离开的原因。",
            "mature_intimacy": {
                "enabled": True,
                "adult_only": True,
                "participants_confirmed_adult": True,
                "consent": "explicit",
                "visual_focus": ["身体距离", "眼神确认", "环境感官细节"],
            },
            "provenance": {
                "title": "creative_suggestion",
                "logline": "source_supported",
                "theme": "creative_suggestion",
                "protagonist_goal": "creative_suggestion",
                "opposition": "creative_suggestion",
                "stakes": "creative_suggestion",
                "climax_choice": "creative_suggestion",
                "ending_hook": "creative_suggestion",
                "emotional_arc": "creative_suggestion",
                "act_structure": "creative_suggestion",
                "pace_chart": "creative_suggestion",
                "visual_motifs": "creative_suggestion",
                "scene_beats": "creative_suggestion",
                "sound_intent": "creative_suggestion",
                "camera_intent": "creative_suggestion",
                "planning_text": "creative_suggestion",
                "mature_intimacy": "creative_suggestion",
            },
        },
    }


def test_reception_rejects_tampered_source_hash(tmp_path: Path) -> None:
    payload = reception()
    payload["source"]["raw_text"] = "被替换的故事"
    path = tmp_path / "reception.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ReceptionError, match="sha256"):
        load_story_reception(path)


def test_reception_requires_adult_consent_guard(tmp_path: Path) -> None:
    payload = reception()
    payload["treatment"]["mature_intimacy"]["adult_only"] = False
    path = tmp_path / "reception.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ReceptionError, match="adult_only"):
        load_story_reception(path)


def test_reception_rejects_minor_intimacy_without_declared_guard(tmp_path: Path) -> None:
    payload = reception("未成年角色卷入成人亲密情节。")
    payload["treatment"].pop("mature_intimacy")
    payload["treatment"]["provenance"].pop("mature_intimacy")
    path = tmp_path / "reception.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ReceptionError, match="minor and intimacy"):
        load_story_reception(path)


def test_reception_rejects_disabled_adult_guard(tmp_path: Path) -> None:
    payload = reception()
    payload["treatment"]["planning_text"] = "两位成年人发生性爱。"
    payload["treatment"]["mature_intimacy"]["enabled"] = False
    path = tmp_path / "reception.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ReceptionError, match="enabled=true"):
        load_story_reception(path)


def test_plan_receive_writes_validated_receipt(tmp_path: Path) -> None:
    payload_path = tmp_path / "reception.json"
    payload_path.write_text(json.dumps(reception(), ensure_ascii=False), encoding="utf-8")
    root = tmp_path / "film"

    code = cmd_plan(
        Namespace(plan_action="receive", root=str(root), file=str(payload_path), force=False)
    )

    assert code == 0
    assert (
        load_story_reception(root / "receipts" / "story-reception.json")["kind"]
        == "story-reception"
    )


def test_received_story_plans_with_original_provenance(tmp_path: Path) -> None:
    payload_path = tmp_path / "reception.json"
    payload_path.write_text(json.dumps(reception(), ensure_ascii=False), encoding="utf-8")
    root = tmp_path / "film"

    report, code = run_plan_cli(
        type(
            "Args",
            (),
            {
                "file": None,
                "text": None,
                "received_file": str(payload_path),
                "title": None,
                "target_duration": 45,
                "apply_film_spec": True,
                "no_film_spec": False,
                "force": True,
                "no_bible": False,
            },
        )(),
        root,
    )

    assert code == 0, report
    normalized = json.loads(
        (root / "receipts" / "story-normalize.json").read_text(encoding="utf-8")
    )
    graph = json.loads((root / "drama-graph.json").read_text(encoding="utf-8"))
    spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
    assert normalized["raw_excerpt"].startswith("成年男女")
    assert normalized["reception"]["source_sha256"] == reception()["source"]["sha256"]
    assert normalized["reception"]["fidelity"]["immutable_facts"] == ["两人是成年人", "在雨夜重逢"]
    assert graph["story"]["theme"] == "亲密来自坦诚选择。"
    assert spec["source_excerpt"].startswith("成年男女")
    assert spec["story_reception"]["fidelity"]["explicit_constraints"] == ["角色关系必须自愿"]
    assert spec["story_reception"]["mature_intimacy"]["adult_only"] is True
