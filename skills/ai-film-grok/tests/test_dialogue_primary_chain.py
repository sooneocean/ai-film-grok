"""Cinema dialogue primary chain: Chinese voice, reverse-shot, no storyteller fill."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def test_normalize_defaults_to_dialogue_drama() -> None:
    from story_plan import normalize_story

    pack = normalize_story("她把门落锁，只剩呼吸和雨声。", title_hint="静")
    assert pack["vo_mode_suggest"] == "dialogue_drama"


def test_prose_interactive_turns_alternate_speakers() -> None:
    from dialogue_screenplay import build_dialogue_screenplay

    sp = build_dialogue_screenplay(
        {
            "title": "互动",
            "genre": "drama",
            "raw_excerpt": "门一响。你还没走？雨还在下。那就别走。",
            "character_candidates": [{"id": "heroine"}, {"id": "partner"}],
            "scene_chunks": [
                {
                    "id": "sc1",
                    "title": "雨",
                    "body": "门一响。你还没走？雨还在下。那就别走。",
                }
            ],
            "dialogue_blocks": [],
        }
    )
    turns = sp["scenes"][0]["dialogue_turns"]
    assert len(turns) >= 2
    assert turns[0]["speaker"] != turns[1]["speaker"]
    assert turns[0]["translation_status"] == "ready"
    assert sp["scenes"][0]["coverage_intent"]["shot_reverse_shot"] is True
    assert sp["scenes"][0]["coverage_intent"]["interactive_pair"] is True


def test_chinese_spoken_and_hf_caption_preference() -> None:
    from render_final import caption_text_for_shot, spoken_text_for_shot, voice_for_shot

    shot = {
        "speaker": "heroine",
        "dialogue": "别走。",
        "caption_text": "别走。",
        "dialogue_ja": "行かないで。",
    }
    assert caption_text_for_shot(shot) == "别走。"
    assert spoken_text_for_shot(shot, dialogue_spoken_lang="zh") == "别走。"
    assert spoken_text_for_shot(shot, dialogue_spoken_lang="ja") == "行かないで。"
    v = voice_for_shot(
        shot,
        default_voice="zh-CN-XiaoxiaoNeural",
        cast_voices={},
        vo_mode="dialogue_drama",
        dialogue_spoken_lang="zh",
    )
    assert v.startswith("zh-CN-")


def test_dialogue_drama_rejects_storyteller_nar() -> None:
    from film_spec import FilmSpecError, validate_film_spec

    spec = {
        "schema_version": 1,
        "title": "t",
        "vo_mode": "dialogue_drama",
        "dialogue_spoken_lang": "zh",
        "narration_spoken_lang": "zh",
        "aspect": "9:16",
        "heat_scale": "soft",
        "director_intent": {
            "logline": "A locked door fills the silence without a narrator.",
            "tone": "drama",
            "emotional_arc": ["a", "b", "c"],
        },
        "transition_sec": 0.25,
        "transition_default": "soft",
        "scenes": [
            {
                "shots": [
                    {
                        "id": "shot01",
                        "dramatic_function": "action",
                        "duration_sec": 3,
                        "screen_mode": "action_cover",
                        "nar": "话说她把门落锁。",
                        "audio_cues": [
                            {"kind": "silence", "start_offset_sec": 0, "duration_sec": 3}
                        ],
                        "dsl": {
                            "subject": "woman",
                            "action": "close door carefully",
                            "motion": "hand on latch door closes",
                            "camera": {"shot_size": "medium"},
                        },
                    }
                ]
            }
        ],
    }
    with pytest.raises(FilmSpecError, match="forbids third-person storyteller nar"):
        validate_film_spec(spec, assign_missing_ids=False)


def test_zh_voice_lock_accepts_chinese_dialogue() -> None:
    from render_final import validate_voice_language_locks

    validate_voice_language_locks(
        [{"id": "f1", "speaker": "heroine", "dialogue": "别走。", "caption_text": "别走。"}],
        dialogue_spoken_lang="zh",
    )
