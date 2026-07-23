"""Tests for P0-3 character bible (protagonist want/need/arc).

Verifies:
- character_bible_strict: true enforces protagonist_want/need/arc in director_intent
- validate_director_intent accepts protagonist fields when present
- drama-graph Character schema extended with dramatic fields
- story_plan _draft_story_contract includes protagonist_want/need/arc
- story_plan character generation includes dramatic role fields
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest
from film_spec import FilmSpecError, validate_director_intent
from story_plan import _draft_story_contract


def _base_spec(**overrides) -> dict:
    spec = {
        "title": "test",
        "vo_mode": "storyteller",
        "director_intent": {
            "logline": "一个关于测试的短片段，至少八个字。",
            "tone": "测试气质",
            "emotional_arc": ["建立", "升温", "爆发"],
        },
        "scenes": [{"shots": []}],
    }
    di_overrides = overrides.pop("di", {})
    spec["director_intent"].update(di_overrides)
    spec.update(overrides)
    return spec


class TestCharacterBibleStrict:
    """character_bible_strict gate in validate_director_intent."""

    def test_strict_requires_protagonist_want(self):
        spec = _base_spec(character_bible_strict=True)
        with pytest.raises(FilmSpecError, match="protagonist_want"):
            validate_director_intent(spec)

    def test_strict_requires_protagonist_need(self):
        spec = _base_spec(character_bible_strict=True)
        spec["director_intent"]["protagonist_want"] = "查明真相"
        with pytest.raises(FilmSpecError, match="protagonist_need"):
            validate_director_intent(spec)

    def test_strict_requires_protagonist_arc(self):
        spec = _base_spec(character_bible_strict=True)
        spec["director_intent"]["protagonist_want"] = "查明真相"
        spec["director_intent"]["protagonist_need"] = "学会信任"
        with pytest.raises(FilmSpecError, match="protagonist_arc"):
            validate_director_intent(spec)

    def test_strict_passes_with_all_three(self):
        spec = _base_spec(character_bible_strict=True)
        spec["director_intent"]["protagonist_want"] = "查明真相"
        spec["director_intent"]["protagonist_need"] = "学会信任"
        spec["director_intent"]["protagonist_arc"] = "孤狼→伙伴"
        intent = validate_director_intent(spec)
        assert intent["protagonist_want"] == "查明真相"
        assert intent["protagonist_need"] == "学会信任"
        assert intent["protagonist_arc"] == "孤狼→伙伴"

    def test_not_strict_no_protagonist_required(self):
        """Without character_bible_strict, protagonist fields are optional."""
        spec = _base_spec()
        intent = validate_director_intent(spec)
        assert "protagonist_want" not in intent

    def test_protagonist_fields_accepted_when_present(self):
        spec = _base_spec()
        spec["director_intent"]["protagonist_want"] = "外在目标"
        spec["director_intent"]["protagonist_need"] = "内在需求"
        spec["director_intent"]["protagonist_arc"] = "A→B"
        intent = validate_director_intent(spec)
        assert intent["protagonist_want"] == "外在目标"

    def test_empty_protagonist_want_rejected(self):
        spec = _base_spec()
        spec["director_intent"]["protagonist_want"] = "   "
        with pytest.raises(FilmSpecError, match="protagonist_want"):
            validate_director_intent(spec)


class TestStoryContractProtagonist:
    """_draft_story_contract includes protagonist fields."""

    def test_draft_has_protagonist_fields(self):
        normalized = {"logline": "test", "genre": "drama"}
        contract = _draft_story_contract(normalized)
        assert "protagonist_want" in contract
        assert "protagonist_need" in contract
        assert "protagonist_arc" in contract
        assert contract["protagonist_want"] == ""

    def test_draft_has_act_structure(self):
        normalized = {"logline": "test", "genre": "drama"}
        contract = _draft_story_contract(normalized)
        assert "act_structure" in contract
        assert "setup_ratio" in contract["act_structure"]


class TestCharacterGeneration:
    """story_plan character generation includes dramatic role fields."""

    def test_characters_have_dramatic_fields(self):
        from story_plan import build_planned_graph, normalize_story

        raw = """
        角色：苏念、陆深

        苏念站在雨夜街头，看着父亲的旧照片。
        陆深走过来递了把伞。
        """
        normalized = normalize_story(raw)
        graph = build_planned_graph(normalized, target_duration=45.0)
        chars = graph.get("characters") or []
        assert len(chars) >= 1
        for ch in chars:
            assert "name" in ch
            assert "want" in ch
            assert "need" in ch
            assert "dramatic_role" in ch
            assert "personality" in ch
            assert "arc_turning_points" in ch
            assert "relationships" in ch

    def test_lead_character_has_authoring_placeholders(self):
        from story_plan import build_planned_graph, normalize_story

        raw = "角色：苏念\n苏念走进雨夜。"
        normalized = normalize_story(raw)
        graph = build_planned_graph(normalized, target_duration=30.0)
        chars = graph.get("characters") or []
        leads = [c for c in chars if c.get("dramatic_role") == "protagonist"]
        assert len(leads) >= 1
        lead = leads[0]
        assert lead["want"] == "needs_authoring"
        assert lead["need"] == "needs_authoring"

    def test_supporting_character_has_empty_want(self):
        """Supporting characters don't get forced authoring placeholders."""
        from story_plan import build_planned_graph, normalize_story

        raw = """
        角色：主角、配角

        主角走进雨夜。
        配角：你好。
        """
        normalized = normalize_story(raw)
        graph = build_planned_graph(normalized, target_duration=30.0)
        chars = graph.get("characters") or []
        supporting = [c for c in chars if c.get("dramatic_role") == "supporting"]
        for s in supporting:
            assert s["want"] == ""
