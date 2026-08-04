"""Motion Prompt Spine — film core into Grok/H3 motion prompts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from motion_prompt_spine import (  # noqa: E402
    MotionCoreError,
    assert_motion_prompt_core,
    build_motion_prompt,
    core_fields,
    ensure_motion_core_in_prompt,
    motion_tier_for,
    want_beat_line,
)
from production_router import build_shot_intent  # noqa: E402
from h3_workflow import _prompt_for_shot  # noqa: E402


def test_want_beat_from_director_intent() -> None:
    spec = {
        "director_intent": {
            "protagonist_want": "她要对方承认爱意",
            "theme": "雨夜对峙",
        }
    }
    shot = {"id": "s1", "dramatic_function": "approach"}
    line = want_beat_line(spec, shot)
    assert "advances want" in line
    assert "approach" in line
    assert "爱意" in line


def test_motion_tier_meat_is_high() -> None:
    assert (
        motion_tier_for(
            {"heat_phase": "act", "wardrobe_state": "bare", "dramatic_function": "action"}
        )
        == "high"
    )
    assert motion_tier_for({"dramatic_function": "reaction"}) == "soft"


def test_build_motion_prompt_includes_df_want_dialogue() -> None:
    spec = {"director_intent": {"protagonist_want": "求他留下"}}
    shot = {
        "id": "s_d",
        "shot_role": "hero",
        "dramatic_function": "climax",
        "heat_phase": "act",
        "screen_mode": "on_camera",
        "dsl": {
            "action": "faces camera and speaks",
            "motion": "subtle head nod",
            "visible_change": "mouth articulates",
            "camera_prompt": "close-up, 85mm, shallow depth",
        },
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "spoken_text": "别走。",
            }
        ],
    }
    prompt = build_motion_prompt(spec, shot, mode="i2v")
    assert "Dramatic function: climax" in prompt
    assert "advances want" in prompt
    assert "别走。" in prompt
    assert "lip sync" in prompt.lower()
    assert "close-up, 85mm" in prompt
    assert "HIGH MOTION" in prompt
    assert_motion_prompt_core(prompt, shot, mode="i2v")


def test_assert_rejects_empty_hero_core() -> None:
    shot = {"id": "empty", "shot_role": "hero"}
    with pytest.raises(MotionCoreError, match="MOTION_CORE"):
        assert_motion_prompt_core("hi", shot, mode="i2v")


def test_ensure_merges_dialogue_into_author_file() -> None:
    shot = {
        "id": "s_x",
        "screen_mode": "on_camera",
        "dramatic_function": "approach",
        "audio_cues": [
            {"kind": "voice", "line_type": "dialogue", "spoken_text": "看着我。"}
        ],
        "dsl": {"action": "soft push-in"},
    }
    out = ensure_motion_core_in_prompt("Vertical 9:16. Keep face. Soft push.", {}, shot)
    assert "看着我。" in out
    assert "Dramatic function: approach" in out


def test_intent_carries_motion_core_fields() -> None:
    intent = build_shot_intent(
        {
            "_i2v_profile": "hybrid_h3",
            "h3": {"enabled": True},
            "director_intent": {"protagonist_want": "夺回控制权"},
        },
        {
            "id": "s_meat",
            "shot_role": "hero",
            "heat_phase": "act",
            "wardrobe_state": "bare",
            "dramatic_function": "action",
            "dsl": {"action": "body rocks", "motion": "thrust rhythm", "visible_change": "weight shifts"},
        },
    )
    assert intent["dramatic_function"] == "action"
    assert intent["motion_tier"] == "high"
    assert intent["has_action_core"] is True
    assert intent["want_beat"] and "夺回控制权" in intent["want_beat"]
    assert "body rocks" in (intent.get("action_summary") or "")


def test_h3_prompt_uses_spine_with_spec(tmp_path: Path) -> None:
    spec = {
        "title": "t",
        "director_intent": {"protagonist_want": "靠近他"},
        "scenes": [
            {
                "id": "sc1",
                "shots": [
                    {
                        "id": "shot01",
                        "shot_role": "hero",
                        "dramatic_function": "approach",
                        "screen_mode": "on_camera",
                        "dsl": {
                            "action": "steps closer",
                            "motion": "slow push-in",
                            "visible_change": "distance shrinks",
                        },
                        "audio_cues": [
                            {
                                "kind": "voice",
                                "line_type": "dialogue",
                                "spoken_text": "过来。",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    (tmp_path / "film-spec.json").write_text(
        __import__("json").dumps(spec, ensure_ascii=False), encoding="utf-8"
    )
    shot = spec["scenes"][0]["shots"][0]
    prompt = _prompt_for_shot(tmp_path, shot, mode="i2v", spec=spec)
    assert "过来。" in prompt
    assert "Dramatic function: approach" in prompt
    assert "advances want" in prompt
    assert (tmp_path / "film-spec.json").is_file()


def test_core_fields_continuity_flag() -> None:
    shot = {
        "id": "s_c",
        "dsl": {"chain_mode": "continue", "action": "keeps turning"},
        "dramatic_function": "action",
    }
    fields = core_fields({}, shot)
    assert fields["continuity_required"] is True
    assert fields["has_action_core"] is True
