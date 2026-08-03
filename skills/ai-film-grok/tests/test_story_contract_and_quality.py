"""Unit tests for story_contract, story_normalize, beat_spine, story_quality, and plan_feedback."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from beat_spine import list_spines, load_spine, spine_exists
from plan_feedback import analyze_evidence
from story_contract import (
    DEFAULT_CONTRACT,
    GENRE_CONTRACT_TEMPLATES,
    _extract_emotional_arc,
    suggest_story_contract,
)
from story_normalize import (
    _character_candidates,
    _clip_nar,
    _dialogue_blocks,
    _draft_story_contract,
    _episode_chunks,
    _extract_plot_point_candidates,
    _location_candidates,
    _scene_chunks,
    _sentences,
    detect_genre,
    detect_heat_signals,
    normalize_story,
    select_beat_spine,
)
from story_quality import (
    check_story_quality,
    score_arc,
    score_conflict,
    score_hook,
    score_payoff,
    score_story,
)


class TestStoryContract:
    def test_default_contract_template(self):
        assert "adult" in GENRE_CONTRACT_TEMPLATES
        assert DEFAULT_CONTRACT == GENRE_CONTRACT_TEMPLATES["adult"]

    def test_suggest_emotional_arc_keywords(self):
        arc1 = _extract_emotional_arc({"raw_excerpt": "主角在痛苦中挣扎，最后陷入恐惧与慌乱"})
        assert any(k in arc1 for k in ["fear", "courage", "克制", "欲望", "恐惧", "迷失"])

        arc2 = _extract_emotional_arc({"raw_excerpt": "毫无关键词的标准对话"})
        assert len(arc2) >= 3

    def test_suggest_story_contract_with_genre(self):
        contract = suggest_story_contract({"raw_excerpt": "复仇与解脱的故事", "genre": "mystery"})
        assert contract["theme"] == "真相与代价"
        assert contract["genre"] == "mystery"


class TestBeatSpine:
    def test_spine_exists(self):
        assert spine_exists("default")
        assert spine_exists("adult_max")
        assert spine_exists("hardcore_male")
        assert spine_exists("dual_climax")
        assert not spine_exists("non_existent_spine_123")

    def test_load_spine(self):
        spine = load_spine("default")
        assert isinstance(spine, list)
        assert len(spine) > 0
        assert "key" in spine[0]

    def test_load_spine_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_spine("non_existent_spine_123")

    def test_list_spines(self):
        spines = list_spines()
        assert "default" in spines
        assert "adult_max" in spines


class TestStoryQuality:
    def test_score_hook(self):
        story_empty = {}
        assert score_hook(story_empty) == 0.0

        story_hook = {"logline": "面对冲突与危险，付出代价决出胜负"}
        assert score_hook(story_hook) > 0.5

    def test_score_conflict(self):
        story = {"opposition": "社会规范", "stakes": "失去一切"}
        assert score_conflict(story) == 1.0

    def test_score_arc(self):
        story_short = {"emotional_arc": ["a", "b"]}
        assert score_arc(story_short) < 1.0

        story_good = {"emotional_arc": ["setup", "confrontation", "resolution"]}
        assert score_arc(story_good) == 1.0

    def test_evaluate_story_quality(self):
        graph = {
            "story": {
                "logline": "面对冲突与危险，付出代价决出胜负",
                "opposition": "极大的阻力",
                "stakes": "生命危险",
                "emotional_arc": ["setup", "confrontation", "resolution"],
                "climax_choice": "勇敢面对",
                "ending_hook": "留下一束光",
                "act_structure": {
                    "setup_ratio": 0.20,
                    "confrontation_ratio": 0.50,
                    "resolution_ratio": 0.30,
                },
            }
        }
        scores = score_story(graph)
        assert scores["overall"] > 0.6
        res = check_story_quality(graph)
        assert res["ok"] is True
        assert "scores" in res


class TestPlanFeedback:
    def test_analyze_evidence_no_data(self):
        res = analyze_evidence(evidence={})
        assert res["status"] == "no_data"

    def test_analyze_evidence_duration_deviation(self):
        evidence = {
            "items": [
                {
                    "evidence_id": "shot_01",
                    "evidence_status": "verified",
                    "planned_duration": 5.0,
                    "executed": {"duration_sec": 8.0},
                }
            ]
        }
        res = analyze_evidence(evidence=evidence)
        assert res["status"] == "ok"
        assert len(res["adjustments"]) == 1
        adj = res["adjustments"][0]
        assert adj["type"] == "duration_deviation"
        assert adj["direction"] == "over"


class TestStoryNormalizeReexports:
    def test_reexports_callable(self):
        assert callable(normalize_story)
        assert callable(detect_genre)
        assert callable(detect_heat_signals)
        assert callable(select_beat_spine)
        assert callable(_draft_story_contract)
        assert callable(_extract_plot_point_candidates)
        assert callable(_character_candidates)
        assert callable(_location_candidates)
        assert callable(_dialogue_blocks)
        assert callable(_scene_chunks)
        assert callable(_episode_chunks)
        assert callable(_sentences)
        assert callable(_clip_nar)
