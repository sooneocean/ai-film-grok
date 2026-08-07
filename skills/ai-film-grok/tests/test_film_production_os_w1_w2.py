"""Film Production OS W1–W2: CreativeIntent, story structure, shot cards, director interpret."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from director_interpretation import (  # noqa: E402
    build_director_interpretation,
    format_director_interpretation_md,
    interpret_scene_at_root,
)
from film_spec import FilmSpecError, validate_director_intent  # noqa: E402
from shot_card import (  # noqa: E402
    SHOT_PURPOSES,
    build_shot_card,
    export_shot_cards,
    format_shot_card_markdown,
    lint_shot_purpose,
    resolve_shot_purpose,
)
from story_structure import (  # noqa: E402
    CODE_SHOTS_WITHOUT_BEAT,
    assert_beats_before_shots,
    validate_story_structure,
    validate_story_structure_at_root,
)


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
    di = overrides.pop("di", {})
    spec["director_intent"].update(di)
    spec.update(overrides)
    return spec


class TestCreativeIntent:
    def test_optional_fields_accepted(self):
        intent = validate_director_intent(
            _base_spec(
                di={
                    "theme": "fear of identity loss",
                    "audience_emotion": "unease → empathy",
                    "protagonist_pov": "Lin Xia",
                    "genre": "psychological thriller",
                    "visual_language": "restrained",
                    "pacing": "slow with shocks",
                }
            )
        )
        assert intent["theme"] == "fear of identity loss"
        assert intent["protagonist_pov"] == "Lin Xia"

    def test_strict_requires_theme(self):
        with pytest.raises(FilmSpecError, match="theme"):
            validate_director_intent(_base_spec(creative_intent_strict=True))

    def test_pacing_falls_back_from_tone(self):
        intent = validate_director_intent(
            _base_spec(
                creative_intent_strict=True,
                di={
                    "theme": "t",
                    "audience_emotion": "a",
                    "protagonist_pov": "p",
                    "genre": "g",
                    "visual_language": "v",
                    # pacing omitted → tone
                },
            )
        )
        assert intent["pacing"] == "测试气质"

    def test_nested_creative_intent_blob(self):
        intent = validate_director_intent(
            _base_spec(
                di={
                    "creative_intent": {
                        "theme": "nested-theme",
                        "audience_emotion": "fear",
                    }
                }
            )
        )
        assert intent["theme"] == "nested-theme"


class TestStoryStructure:
    def test_flags_missing_goal_non_strict(self):
        report = validate_story_structure({"story": {}}, strict=False)
        assert report["ok"] is True
        assert "STORY_NO_PROTAGONIST_GOAL" in report["codes"]

    def test_strict_blocks_without_goal(self):
        report = validate_story_structure(
            {
                "story": {
                    "protagonist_goal": "get drive",
                    "opposition": "pursuer",
                    "stakes": "identity",
                    "emotional_arc": ["a", "b", "c"],
                },
                "episodes": [
                    {
                        "scenes": [
                            {
                                "id": "SC_01",
                                "scene_turn": "drive is fake",
                                "beats": [{"id": "bt1", "shots": [{"id": "sh1"}]}],
                            }
                        ]
                    }
                ],
            },
            strict=True,
        )
        assert report["ok"] is True

    def test_strict_fails_empty_story(self):
        report = validate_story_structure({"story": {}}, strict=True)
        assert report["ok"] is False
        assert report["blocking"]

    def test_shots_without_beat_flagged(self):
        report = validate_story_structure(
            {},
            spec={
                "scenes": [
                    {
                        "id": "sc01",
                        "shots": [
                            {"id": "s1", "dramatic_function": "hook"},
                            {"id": "s2", "dramatic_function": "action"},
                        ],
                    }
                ]
            },
            strict=True,
            require_beats=True,
        )
        assert CODE_SHOTS_WITHOUT_BEAT in report["codes"] or report.get("beatless_scene_ids")

    def test_assert_beats_before_shots(self):
        report = assert_beats_before_shots(
            {},
            spec={"scenes": [{"id": "sc01", "shots": [{"id": "s1"}]}]},
            strict=True,
        )
        assert report["ok"] is False
        assert report["media_spend_allowed"] is False

    def test_receipt_at_root(self, tmp_path: Path):
        (tmp_path / "drama-graph.json").write_text(
            json.dumps(
                {
                    "story": {
                        "protagonist_goal": "goal",
                        "opposition": "opp",
                        "stakes": "stakes",
                        "emotional_arc": ["a", "b", "c"],
                    },
                    "episodes": [],
                }
            ),
            encoding="utf-8",
        )
        report = validate_story_structure_at_root(tmp_path, strict=False)
        assert report["ok"] is True
        assert (tmp_path / "receipts" / "story-structure.json").is_file()


class TestShotCard:
    def test_purpose_from_dramatic_function(self):
        assert resolve_shot_purpose({"dramatic_function": "reaction"}) == "show_reaction"

    def test_aesthetic_purpose_rejected(self):
        report = lint_shot_purpose(
            [{"id": "s1", "shot_purpose": "cinematic", "dramatic_function": "hook"}]
        )
        assert report["ok"] is False
        assert "SHOT_PURPOSE_AESTHETIC_ONLY" in report["codes"]

    def test_purpose_enum_complete(self):
        assert "reveal_information" in SHOT_PURPOSES
        assert "dialogue_coverage" in SHOT_PURPOSES

    def test_build_card_and_markdown(self):
        card = build_shot_card(
            {
                "id": "SC012_SH050",
                "dramatic_function": "action",
                "shot_purpose": "story_reveal",
                "dsl": {"visible_change": "red mark on drive", "shot_size": "close_up"},
                "duration_sec": 4.5,
                "continuity_in": {"hand": "bandaged"},
            },
            scene_id="SC_012",
            beat_id="BT_04",
        )
        assert card["shot_purpose"] == "story_reveal"
        assert card["continuity_in"]["hand"] == "bandaged"
        md = format_shot_card_markdown(card, index=1)
        assert "Shot 01" in md
        assert "story_reveal" in md

    def test_export_shot_cards(self, tmp_path: Path):
        spec = {
            "title": "Garage",
            "scenes": [
                {
                    "id": "SC_01",
                    "shots": [
                        {
                            "id": "sh01",
                            "dramatic_function": "hook",
                            "dsl": {"visible_change": "enters garage"},
                            "duration_sec": 3,
                        }
                    ],
                }
            ],
        }
        (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
        report = export_shot_cards(tmp_path, write_files=True)
        assert report["ok"] is True
        assert report["count"] == 1
        assert (tmp_path / "shot-cards" / "SHOT_LIST.md").is_file()
        assert (tmp_path / "shot-cards" / "sh01.json").is_file()


class TestDirectorInterpretation:
    def test_build_from_board(self):
        payload = build_director_interpretation(
            {
                "director_intent": {
                    "logline": "x" * 10,
                    "tone": "tense",
                    "emotional_arc": ["unease", "dread", "shock"],
                    "theme": "identity",
                    "visual_language": "unstable",
                    "protagonist_pov": "Lin",
                },
                "scenes": [
                    {
                        "id": "SC_012",
                        "title": "Parking",
                        "director_board": {
                            "emotional_turn": "tense → panic",
                            "audience_question": "is the drive real?",
                            "coverage_strategy": "wide → CU insert",
                            "cut_intent": "hold on reveal",
                        },
                    }
                ],
            },
            scene_id="SC_012",
        )
        assert payload["scene_id"] == "SC_012"
        assert "panic" in payload["emotional_arc"] or "tense" in payload["dramatic_function"]
        md = format_director_interpretation_md(payload)
        assert "Director Interpretation" in md
        assert "### POV" in md

    def test_write_receipt(self, tmp_path: Path):
        (tmp_path / "film-spec.json").write_text(
            json.dumps(
                {
                    "title": "t",
                    "director_intent": {
                        "logline": "x" * 10,
                        "tone": "t",
                        "emotional_arc": ["a", "b", "c"],
                    },
                    "scenes": [{"id": "sc01", "title": "One"}],
                }
            ),
            encoding="utf-8",
        )
        report = interpret_scene_at_root(tmp_path, scene_id="sc01")
        assert report["ok"] is True
        assert Path(report["receipt"]).is_file()
        assert Path(report["markdown"]).is_file()


class TestDramaticMeaningAestheticHook:
    def test_lint_shot_meaning_merges_aesthetic_purpose(self):
        from dramatic_meaning import lint_shot_meaning

        report = lint_shot_meaning(
            [
                {
                    "id": "s1",
                    "dramatic_function": "hook",
                    "shot_purpose": "looks cool",
                    "dsl": {"visible_change": "she enters"},
                }
            ]
        )
        assert report["ok"] is False
        assert "SHOT_PURPOSE_AESTHETIC_ONLY" in report["codes"]
