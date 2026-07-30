from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import jsonschema

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dialogue_screenplay import (  # noqa: E402
    build_dialogue_screenplay,
    validate_dialogue_screenplay,
)


def _normalized(**overrides):
    payload = {
        "schema_version": 1,
        "kind": "normalized-story",
        "title": "末班车",
        "genre": "drama",
        "raw_excerpt": "雨夜的末班车停在终点站。阿澄发现照片背后写着自己的名字。",
        "source_evidence_refs": ["source:story.txt"],
        "scene_chunks": [
            {
                "title": "末班车内",
                "body": "雨夜的末班车停在终点站。阿澄发现照片背后写着自己的名字。",
            }
        ],
        "dialogue_blocks": [],
    }
    payload.update(overrides)
    return payload


def _approved_screenplay():
    screenplay = build_dialogue_screenplay(
        _normalized(
            raw_excerpt="阿澄：你为什么还没下车？\n乘客：因为照片背后写着你的名字。",
            dialogue_blocks=[
                {"id": "dlg_01", "speaker": "阿澄", "text": "你为什么还没下车？"},
                {
                    "id": "dlg_02",
                    "speaker": "乘客",
                    "text": "因为照片背后写着你的名字。",
                },
            ],
        )
    )
    screenplay["status"] = "reviewed"
    screenplay["review_status"] = "approved"
    scene = screenplay["scenes"][0]
    scene.update(
        {
            "scene_goal": "阿澄确认乘客留下的原因",
            "conflict": "乘客掌握阿澄不知道的信息",
            "emotional_turn": "戒备转为震惊",
            "time_space": {"time": "雨夜", "location": "末班车内"},
            "review_status": "approved",
        }
    )
    for turn, japanese in zip(
        scene["dialogue_turns"],
        ("どうしてまだ降りないの？", "写真の裏に君の名前があるから。"),
        strict=True,
    ):
        turn.update(
            {
                "addressee": "对方",
                "dialogue_ja": japanese,
                "translation_status": "ready",
                "review_status": "approved",
                "duration_sec": 2.0,
                "scene_state_id": f"state_{turn['line_id']}",
            }
        )
    return screenplay


def test_prose_defaults_to_candidate_dialogue_without_claiming_source_authorship():
    screenplay = build_dialogue_screenplay(_normalized())

    assert screenplay["mode"] == "dialogue_drama"
    assert screenplay["status"] == "candidate_only"
    assert screenplay["source_refs"] == ["source:story.txt"]
    assert len(screenplay["scenes"]) == 1
    scene = screenplay["scenes"][0]
    assert set(
        (
            "scene_id",
            "scene_goal",
            "conflict",
            "emotional_turn",
            "time_space",
            "dialogue_turns",
            "coverage_intent",
            "narration_gaps",
        )
    ).issubset(scene)
    turn = scene["dialogue_turns"][0]
    assert turn["provenance"] == "creative_suggestion"
    assert turn["dialogue_zh"] in _normalized()["raw_excerpt"]
    assert turn["source_evidence"]["source_excerpt"] == turn["dialogue_zh"]
    assert turn["speaker"] == "pending_cast"
    assert turn["dialogue_ja"] == ""
    assert turn["translation_status"] == "pending"


def test_explicit_dialogue_round_trips_speaker_and_source_text():
    screenplay = build_dialogue_screenplay(
        _normalized(
            raw_excerpt="阿澄：别走。\n莲：我必须走。",
            dialogue_blocks=[
                {"id": "line_a", "speaker": "阿澄", "text": "别走。"},
                {
                    "id": "line_b",
                    "speaker": "莲",
                    "addressee": "阿澄",
                    "text": "行かなければならない。",
                    "subtitle_zh": "我必须走。",
                    "language": "ja",
                },
            ],
        )
    )

    turns = screenplay["scenes"][0]["dialogue_turns"]
    assert [turn["line_id"] for turn in turns] == ["line_a", "line_b"]
    assert [turn["speaker"] for turn in turns] == ["阿澄", "莲"]
    assert turns[0]["dialogue_zh"] == "别走。"
    assert turns[0]["translation_status"] == "pending"
    assert turns[1]["dialogue_ja"] == "行かなければならない。"
    assert turns[1]["subtitle_zh"] == "我必须走。"
    assert turns[1]["translation_status"] == "ready"
    assert turns[1]["provenance"] == "source_supported"


def test_strict_accepts_reviewed_grounded_translated_dialogue():
    report = validate_dialogue_screenplay(_approved_screenplay(), strict=True)

    assert report["ok"], report
    assert report["issues"] == []
    assert report["metrics"]["dialogue_turns"] == 2
    assert report["metrics"]["narration_ratio"] == 0.0


def test_strict_rejects_candidate_missing_translation_and_source():
    screenplay = _approved_screenplay()
    screenplay["status"] = "candidate_only"
    screenplay["review_status"] = "pending"
    turn = screenplay["scenes"][0]["dialogue_turns"][0]
    turn["dialogue_ja"] = ""
    turn["translation_status"] = "pending"
    turn["source_evidence"]["source_refs"] = []

    report = validate_dialogue_screenplay(screenplay, strict=True)
    codes = {issue["code"] for issue in report["issues"]}

    assert report["ok"] is False
    assert "SCREENPLAY_REVIEW_REQUIRED" in codes
    assert "DIALOGUE_TRANSLATION_PENDING" in codes
    assert "SOURCE_EVIDENCE_REQUIRED" in codes
    assert all(set(issue) == {"code", "message", "node_ref"} for issue in report["issues"])


def test_strict_rejects_narration_without_reason_or_uncovered_information():
    screenplay = _approved_screenplay()
    gap = {
        "gap_id": "nar_01",
        "text_zh": "三天后。",
        "narration_reason": "",
        "uncovered_information": "",
        "duration_sec": 0.5,
        "source_evidence": {
            "source_refs": ["source:story.txt"],
            "source_excerpt": "三天后",
            "provenance": "source_supported",
        },
        "duplicates_dialogue_or_visual": False,
        "visual_information": "",
        "review_status": "approved",
    }
    screenplay["narration_gaps"] = [gap]
    screenplay["scenes"][0]["narration_gaps"] = [deepcopy(gap)]

    report = validate_dialogue_screenplay(screenplay, strict=True)
    codes = {issue["code"] for issue in report["issues"]}

    assert "NARRATION_REASON_REQUIRED" in codes
    assert "NARRATION_INFORMATION_GAP_REQUIRED" in codes


def test_strict_rejects_repeated_and_over_budget_narration():
    screenplay = _approved_screenplay()
    repeated_text = screenplay["scenes"][0]["dialogue_turns"][0]["subtitle_zh"]
    gap = {
        "gap_id": "nar_01",
        "text_zh": repeated_text,
        "narration_reason": "time_jump",
        "uncovered_information": "三天时间已经过去",
        "duration_sec": 1.0,
        "source_evidence": {
            "source_refs": ["source:story.txt"],
            "source_excerpt": "三天后",
            "provenance": "source_supported",
        },
        "duplicates_dialogue_or_visual": False,
        "visual_information": "",
        "review_status": "approved",
    }
    screenplay["narration_gaps"] = [gap]
    screenplay["scenes"][0]["narration_gaps"] = [deepcopy(gap)]

    report = validate_dialogue_screenplay(screenplay, strict=True)
    codes = {issue["code"] for issue in report["issues"]}

    assert "NARRATION_DUPLICATES_STORY" in codes
    assert "NARRATION_BUDGET_EXCEEDED" in codes
    assert report["metrics"]["narration_ratio"] == 0.2


def test_strict_rejects_empty_or_zero_duration_narration():
    screenplay = _approved_screenplay()
    gap = {
        "gap_id": "nar_01",
        "text_zh": "",
        "narration_reason": "time_jump",
        "uncovered_information": "三天时间已经过去",
        "duration_sec": 0,
        "source_evidence": {
            "source_refs": ["source:story.txt"],
            "source_excerpt": "三天后",
            "provenance": "source_supported",
        },
        "duplicates_dialogue_or_visual": False,
        "visual_information": "",
        "review_status": "approved",
    }
    screenplay["narration_gaps"] = [gap]

    report = validate_dialogue_screenplay(screenplay, strict=True)
    codes = {issue["code"] for issue in report["issues"]}

    assert {"NARRATION_TEXT_REQUIRED", "NARRATION_DURATION_REQUIRED"} <= codes


def test_documentary_and_explicit_monologue_are_mode_exceptions():
    documentary = build_dialogue_screenplay(_normalized(genre="documentary"))
    monologue = build_dialogue_screenplay(
        _normalized(story_mode="monologue", explicit_monologue=True)
    )

    assert documentary["mode"] == "storyteller"
    assert documentary["mode_exception"] == "documentary"
    assert documentary["scenes"][0]["dialogue_turns"] == []
    assert monologue["mode"] == "monologue"
    assert monologue["mode_exception"] == "explicit_monologue"


def test_non_strict_reports_shape_errors_without_enforcing_review_gate():
    screenplay = build_dialogue_screenplay(_normalized())
    report = validate_dialogue_screenplay(screenplay, strict=False)

    assert report["ok"], report
    assert report["metrics"]["scenes"] == 1
    assert report["metrics"]["candidate_only"] is True


def test_builder_output_conforms_to_dialogue_screenplay_schema():
    schema_path = SCRIPTS.parent / "schemas" / "dialogue-screenplay.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    jsonschema.Draft202012Validator(schema).validate(build_dialogue_screenplay(_normalized()))
