"""Tests for P0-1 multi-genre beat spines (de-type-bias).

Verifies:
- detect_genre() signal inference for each genre
- select_beat_spine() returns correct spine per genre via beat_spine loader
- JSON spines all use valid dramatic_function enum values
- normalize_story() includes genre field
- backward compat: no genre → adult default (unchanged behavior)
- dramatic_function enum unchanged (write-spec compatibility)
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from story_plan import (
    DRAMATIC_FUNCS,
    GENRES,
    detect_genre,
    detect_heat_signals,
    normalize_story,
    select_beat_spine,
)

from beat_spine import list_spines, load_spine, spine_exists

# ---------------------------------------------------------------------------
# Beat spine loader validation
# ---------------------------------------------------------------------------


class TestBeatSpineLoader:
    """beat_spine loader can find all expected spine files."""

    def test_loader_finds_default(self):
        assert spine_exists("default")

    def test_loader_finds_adult_max(self):
        assert spine_exists("adult_max")

    def test_loader_finds_hardcore_male(self):
        assert spine_exists("hardcore_male")

    def test_loader_finds_dual_climax(self):
        assert spine_exists("dual_climax")

    def test_loader_finds_all_genres(self):
        for g in GENRES:
            if g == "adult":
                continue
            assert spine_exists(g), f"genre '{g}' spine JSON missing"

    def test_list_spines_includes_all(self):
        names = list_spines()
        assert "default" in names
        assert "adult_max" in names

    def test_load_spine_returns_valid_list(self):
        spine = load_spine("drama")
        assert isinstance(spine, list)
        assert len(spine) > 0
        for beat in spine:
            assert "key" in beat
            assert "dramatic_function" in beat


# ---------------------------------------------------------------------------
# GENRE_SPINES structural validation (via JSON loader)
# ---------------------------------------------------------------------------


class TestGenreSpineStructure:
    """Every genre spine must use valid dramatic_function values."""

    def test_all_genres_have_spines(self):
        for g in GENRES:
            if g == "adult":
                continue
            assert spine_exists(g), f"genre '{g}' missing spine JSON"

    def test_spine_beats_use_valid_enum(self):
        for g in GENRES:
            if g == "adult":
                continue
            spine = load_spine(g)
            for beat in spine:
                df = beat.get("dramatic_function")
                assert df in DRAMATIC_FUNCS, (
                    f"genre '{g}' beat '{beat.get('key')}' has invalid "
                    f"dramatic_function '{df}' — must be in {DRAMATIC_FUNCS}"
                )

    def test_spine_weights_sum_near_one(self):
        for g in GENRES:
            if g == "adult":
                continue
            spine = load_spine(g)
            total = sum(float(b.get("weight", 0)) for b in spine)
            assert 0.95 <= total <= 1.05, f"genre '{g}' weights sum={total:.3f}, expected ~1.0"

    def test_spine_has_required_keys(self):
        required = {"key", "dramatic_function", "importance", "objective", "weight", "shots_n"}
        for g in GENRES:
            if g == "adult":
                continue
            spine = load_spine(g)
            for beat in spine:
                missing = required - set(beat.keys())
                assert not missing, f"genre '{g}' beat '{beat.get('key')}' missing keys: {missing}"


# ---------------------------------------------------------------------------
# detect_genre()
# ---------------------------------------------------------------------------


class TestDetectGenre:
    """Genre signal detection from brief text."""

    def test_drama_signals(self):
        result = detect_genre("一个关于家庭伦理与现实生活的剧情短片")
        assert result["genre"] == "drama"
        assert result["evidence"] == "text_markers"

    def test_mystery_signals(self):
        result = detect_genre("悬疑推理：雨夜出租车里的凶杀案调查")
        assert result["genre"] == "mystery"
        assert result["evidence"] == "text_markers"

    def test_arthouse_signals(self):
        result = detect_genre("一部文艺实验片，充满诗意与留白的意象")
        assert result["genre"] == "arthouse"
        assert result["evidence"] == "text_markers"

    def test_documentary_signals(self):
        result = detect_genre("纪录片：城市边缘人物的真实访谈纪实")
        assert result["genre"] == "documentary"
        assert result["evidence"] == "text_markers"

    def test_adult_heat_signals_priority(self):
        """Adult heat signals take priority over genre markers."""
        heat = detect_heat_signals("成人办事短剧，尺度拉满，落锁加演")
        result = detect_genre("成人办事短剧，尺度拉满", heat=heat)
        assert result["genre"] == "adult"
        assert result["evidence"] == "heat_signals"

    def test_explicit_genre_overrides_heat(self):
        """Explicit genre field wins over heat signals."""
        heat = detect_heat_signals("成人办事短剧，尺度拉满")
        result = detect_genre("成人办事短剧", heat=heat, explicit_genre="drama")
        assert result["genre"] == "drama"
        assert result["evidence"] == "explicit_field"

    def test_default_is_adult(self):
        """No signals → default adult (backward compat)."""
        result = detect_genre("雨夜出租车里的一次对话")
        assert result["genre"] == "adult"
        assert result["evidence"] == "default"

    def test_multiple_genre_signals_warning(self):
        result = detect_genre("一部悬疑推理纪录片，案件调查纪实")
        assert result["genre"] in ("mystery", "documentary")
        assert len(result["warnings"]) >= 1
        assert "multiple genre" in result["warnings"][0]


# ---------------------------------------------------------------------------
# select_beat_spine()
# ---------------------------------------------------------------------------


class TestSelectBeatSpine:
    """Beat spine selection by genre."""

    def test_drama_spine(self):
        spine = select_beat_spine(genre="drama")
        assert len(spine) == 6
        assert spine[0]["dramatic_function"] == "hook"
        assert spine[-1]["dramatic_function"] == "afterglow"
        assert spine[0]["key"] == "hook"
        assert spine[-1]["key"] == "resolution"

    def test_mystery_spine(self):
        spine = select_beat_spine(genre="mystery")
        assert len(spine) == 6
        assert spine[2]["dramatic_function"] == "sensory"
        assert spine[2]["key"] == "clue"

    def test_arthouse_spine(self):
        spine = select_beat_spine(genre="arthouse")
        assert len(spine) == 6
        assert spine[1]["dramatic_function"] == "sensory"
        assert spine[1]["key"] == "observe"

    def test_documentary_spine(self):
        spine = select_beat_spine(genre="documentary")
        assert len(spine) == 6
        assert spine[2]["dramatic_function"] == "sensory"
        assert spine[2]["key"] == "evidence"

    def test_adult_default_backward_compat(self):
        """No genre → adult default pins adult_max (2026-07-29 IRON)."""
        spine = select_beat_spine()
        assert "act" in [b.get("heat_phase") for b in spine]

    def test_soft_heat_uses_default_spine(self):
        """Explicit soft cool-down keeps default spine."""
        spine = select_beat_spine({"heat_scale": "soft"}, genre="adult")
        assert spine[0]["key"] == "hook"
        assert spine[-1]["key"] == "button"

    def test_adult_explicit_genre_uses_heat_logic(self):
        """genre=adult with heat → adult_max spine (backward compat)."""
        spine = select_beat_spine({"heat_scale": "max"}, genre="adult")
        assert "act" in [b.get("heat_phase") for b in spine]

    def test_non_adult_genre_ignores_heat(self):
        """Non-adult genre ignores heat signals (no adult spine)."""
        spine = select_beat_spine({"heat_scale": "max"}, genre="mystery")
        assert len(spine) == 6
        assert spine[0]["key"] == "hook"

    def test_spine_returned_is_copy_not_reference(self):
        """Modifying returned spine must not affect the JSON source."""
        spine = select_beat_spine(genre="drama")
        original_weight = spine[0]["weight"]
        spine[0]["weight"] = 999.0
        # Re-load from JSON — should be unchanged
        spine2 = select_beat_spine(genre="drama")
        assert spine2[0]["weight"] == original_weight


# ---------------------------------------------------------------------------
# normalize_story() includes genre
# ---------------------------------------------------------------------------


class TestNormalizeStoryGenre:
    """normalize_story() must detect and return genre."""

    def test_normalize_includes_genre_field(self):
        result = normalize_story("悬疑推理：雨夜的凶杀案调查")
        assert "genre" in result
        assert result["genre"] == "mystery"

    def test_normalize_adult_default(self):
        result = normalize_story("雨夜出租车里的一次对话")
        assert result.get("genre") == "adult"

    def test_normalize_genre_evidence(self):
        result = normalize_story("一部家庭剧情短片")
        assert result.get("genre") == "drama"
        assert result.get("genre_evidence") == "text_markers"

    def test_normalize_adult_heat_overrides_genre_markers(self):
        """If brief has both drama markers and adult heat signals, genre=adult."""
        result = normalize_story("成人办事短剧，关于家庭伦理的现实剧情，尺度拉满")
        assert result.get("genre") == "adult"


# ---------------------------------------------------------------------------
# dramatic_function enum unchanged (write-spec compatibility)
# ---------------------------------------------------------------------------


class TestDramaticFunctionEnumUnchanged:
    """The 7-value enum must not change — write-spec gate depends on it."""

    def test_enum_has_seven_values(self):
        assert len(DRAMATIC_FUNCS) == 7

    def test_enum_values(self):
        expected = ("hook", "approach", "sensory", "reaction", "action", "afterglow", "bridge")
        assert expected == DRAMATIC_FUNCS

    def test_all_genre_spines_use_enum_only(self):
        """No genre spine introduces a dramatic_function outside the enum."""
        for g in GENRES:
            if g == "adult":
                continue
            spine = load_spine(g)
            for beat in spine:
                assert beat["dramatic_function"] in DRAMATIC_FUNCS


class TestSelectBeatSpineAutoDiscovery:
    """select_beat_spine() auto-discovers genre spines from JSON files."""

    def test_auto_discovers_non_genre_spine_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A spine JSON that is not in GENRES (e.g. thriller) is still found
        via file-based auto-discovery (beat_spine.SCHEMA_DIR)."""
        import beat_spine

        # Create a temporary thriller spine file in a fake schema dir
        thriller_spine = [
            {
                "key": "hook",
                "dramatic_function": "hook",
                "importance": "climax",
                "objective": "悬念开场",
                "weight": 0.15,
                "shots_n": 1,
            },
            {
                "key": "tension",
                "dramatic_function": "sensory",
                "importance": "important",
                "objective": "紧张升级",
                "weight": 0.35,
                "shots_n": 2,
            },
            {
                "key": "climax",
                "dramatic_function": "action",
                "importance": "climax",
                "objective": "真相揭露",
                "weight": 0.35,
                "shots_n": 2,
            },
            {
                "key": "resolution",
                "dramatic_function": "afterglow",
                "importance": "supporting",
                "objective": "余韵",
                "weight": 0.15,
                "shots_n": 1,
            },
        ]
        fake_schema = tmp_path / "beat-spines"
        fake_schema.mkdir()
        (fake_schema / "thriller.json").write_text(
            json.dumps(thriller_spine, ensure_ascii=False), encoding="utf-8"
        )
        monkeypatch.setattr(beat_spine, "SCHEMA_DIR", fake_schema)

        # spine_exists and load_spine now look in the fake dir
        assert beat_spine.spine_exists("thriller")
        spine = select_beat_spine(genre="thriller")
        assert len(spine) == 4
        assert spine[0]["key"] == "hook"
        assert spine[2]["key"] == "climax"
        assert spine[3]["key"] == "resolution"
