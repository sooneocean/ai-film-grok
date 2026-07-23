"""Tests for P0-2 three-act structure + pace chart parameterization.

Verifies:
- act_structure schema field with ratio validation (sum≈1.0)
- pace_chart structured entries (label/start_ratio/end_ratio/cut_freq/intensity)
- validate_director_intent accepts structured act_structure + pace_chart
- pace_chart_strict: true enforces non-empty + ≥3 segments
- act_structure_strict: true enforces setup/confrontation/resolution
- backward compat: legacy string pace_chart still accepted
- backward compat: act_structure/pace_chart optional when not strict
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from film_spec import FilmSpecError, validate_director_intent


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
    spec.update(overrides)
    di = spec["director_intent"]
    di.update(overrides.pop("di", {}))
    return spec


class TestActStructureValidation:
    """act_structure object validation in validate_director_intent."""

    def test_act_structure_accepted_when_present(self):
        spec = _base_spec()
        spec["director_intent"]["act_structure"] = {
            "setup": "世界建立",
            "confrontation": "冲突升级",
            "resolution": "高潮解决",
            "setup_ratio": 0.20,
            "confrontation_ratio": 0.50,
            "resolution_ratio": 0.30,
        }
        intent = validate_director_intent(spec)
        assert "act_structure" in intent
        assert intent["act_structure"]["setup"] == "世界建立"

    def test_act_structure_ratio_sum_must_be_near_one(self):
        spec = _base_spec()
        spec["director_intent"]["act_structure"] = {
            "setup_ratio": 0.50,
            "confrontation_ratio": 0.50,
            "resolution_ratio": 0.50,
        }
        try:
            validate_director_intent(spec)
            raise AssertionError("should have raised FilmSpecError")
        except FilmSpecError as e:
            assert "ratios sum" in str(e).lower()

    def test_act_structure_ratio_out_of_range(self):
        spec = _base_spec()
        spec["director_intent"]["act_structure"] = {
            "setup_ratio": 0.80,
        }
        try:
            validate_director_intent(spec)
            raise AssertionError("should have raised FilmSpecError")
        except FilmSpecError as e:
            assert "out of range" in str(e).lower()

    def test_act_structure_optional_when_not_strict(self):
        """act_structure is optional when act_structure_strict is not set."""
        spec = _base_spec()
        intent = validate_director_intent(spec)
        assert "act_structure" not in intent

    def test_act_structure_strict_requires_fields(self):
        spec = _base_spec()
        spec["act_structure_strict"] = True
        try:
            validate_director_intent(spec)
            raise AssertionError("should have raised FilmSpecError")
        except FilmSpecError as e:
            assert "act_structure" in str(e).lower()

    def test_act_structure_strict_rejects_partial_act(self):
        spec = _base_spec()
        spec["act_structure_strict"] = True
        spec["director_intent"]["act_structure"] = {"setup": "建立世界"}
        try:
            validate_director_intent(spec)
            raise AssertionError("should have raised FilmSpecError")
        except FilmSpecError as e:
            assert "confrontation" in str(e)
            assert "resolution" in str(e)


class TestPaceChartValidation:
    """pace_chart structured entry validation."""

    def test_structured_pace_chart_accepted(self):
        spec = _base_spec()
        spec["director_intent"]["pace_chart"] = [
            {
                "label": "慢燃",
                "start_ratio": 0.0,
                "end_ratio": 0.25,
                "cut_freq": "slow",
                "intensity": 3,
            },
            {
                "label": "加速",
                "start_ratio": 0.25,
                "end_ratio": 0.55,
                "cut_freq": "medium",
                "intensity": 6,
            },
            {
                "label": "高潮",
                "start_ratio": 0.55,
                "end_ratio": 0.80,
                "cut_freq": "rapid",
                "intensity": 9,
            },
        ]
        intent = validate_director_intent(spec)
        assert len(intent["pace_chart"]) == 3
        assert intent["pace_chart"][0]["label"] == "慢燃"
        assert intent["pace_chart"][2]["intensity"] == 9.0

    def test_legacy_string_pace_chart_accepted(self):
        """Legacy string array format still works (backward compat)."""
        spec = _base_spec()
        spec["director_intent"]["pace_chart"] = ["慢燃", "加速", "高潮", "释放"]
        intent = validate_director_intent(spec)
        assert len(intent["pace_chart"]) == 4
        assert intent["pace_chart"][0] == "慢燃"

    def test_pace_chart_end_before_start_rejected(self):
        spec = _base_spec()
        spec["director_intent"]["pace_chart"] = [
            {"label": "bad", "start_ratio": 0.5, "end_ratio": 0.3},
        ]
        try:
            validate_director_intent(spec)
            raise AssertionError("should have raised FilmSpecError")
        except FilmSpecError as e:
            assert "end_ratio must be > start_ratio" in str(e)

    def test_pace_chart_intensity_out_of_range(self):
        spec = _base_spec()
        spec["director_intent"]["pace_chart"] = [
            {"label": "x", "start_ratio": 0.0, "end_ratio": 0.5, "intensity": 15},
        ]
        try:
            validate_director_intent(spec)
            raise AssertionError("should have raised FilmSpecError")
        except FilmSpecError as e:
            assert "intensity" in str(e).lower()

    def test_pace_chart_optional_when_not_strict(self):
        spec = _base_spec()
        intent = validate_director_intent(spec)
        assert "pace_chart" not in intent

    def test_pace_chart_strict_requires_non_empty(self):
        spec = _base_spec()
        spec["pace_chart_strict"] = True
        try:
            validate_director_intent(spec)
            raise AssertionError("should have raised FilmSpecError")
        except FilmSpecError as e:
            assert "pace_chart" in str(e).lower()

    def test_pace_chart_strict_requires_min_3_segments(self):
        spec = _base_spec()
        spec["pace_chart_strict"] = True
        spec["director_intent"]["pace_chart"] = [
            {"label": "only one", "start_ratio": 0.0, "end_ratio": 1.0},
        ]
        try:
            validate_director_intent(spec)
            raise AssertionError("should have raised FilmSpecError")
        except FilmSpecError as e:
            assert "≥3" in str(e) or "3" in str(e)

    def test_pace_chart_ratio_out_of_range(self):
        spec = _base_spec()
        spec["director_intent"]["pace_chart"] = [
            {"label": "x", "start_ratio": -0.1, "end_ratio": 0.5},
        ]
        try:
            validate_director_intent(spec)
            raise AssertionError("should have raised FilmSpecError")
        except FilmSpecError as e:
            assert "start_ratio" in str(e).lower()


class TestStoryContractActStructure:
    """_draft_story_contract should initialize act_structure."""

    def test_draft_story_contract_has_act_structure(self):
        from story_plan import _draft_story_contract

        normalized = {"logline": "test logline", "genre": "drama"}
        contract = _draft_story_contract(normalized)
        assert "act_structure" in contract
        assert contract["act_structure"]["setup_ratio"] == 0.20
        assert contract["act_structure"]["confrontation_ratio"] == 0.50
        assert contract["act_structure"]["resolution_ratio"] == 0.30
