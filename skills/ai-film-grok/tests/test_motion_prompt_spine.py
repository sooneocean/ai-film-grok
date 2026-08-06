"""Motion Prompt Spine — film core into Grok/H3 motion prompts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from h3_workflow import _prompt_for_shot  # noqa: E402
from motion_prompt_spine import (  # noqa: E402
    MotionCoreError,
    assert_motion_prompt_core,
    build_h3_temporal_prompt,
    build_motion_prompt,
    core_fields,
    ensure_motion_core_in_prompt,
    motion_tier_for,
    want_beat_line,
)
from production_router import build_shot_intent  # noqa: E402


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
        "audio_cues": [{"kind": "voice", "line_type": "dialogue", "spoken_text": "看着我。"}],
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
            "dsl": {
                "action": "body rocks",
                "motion": "thrust rhythm",
                "visible_change": "weight shifts",
            },
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


# ── H3 temporal prompt builder tests ──────────────────────────────────────


def test_h3_temporal_prompt_has_timecodes() -> None:
    """Temporal prompt must contain [Xs-Ys] timecode segments."""
    shot = {
        "id": "s_temporal",
        "dramatic_function": "approach",
        "dsl": {"action": "walks toward camera", "camera_prompt": "medium shot"},
    }
    prompt = build_h3_temporal_prompt({}, shot, duration_sec=8)
    assert "[0s-" in prompt
    assert "]" in prompt


def test_h3_temporal_prompt_segments_contiguous() -> None:
    """Segments must cover the full duration with no gaps."""
    from h3_timeline_prompt import validate_timeline_coverage

    shot = {
        "id": "s_contig",
        "dramatic_function": "approach",
        "dsl": {"action": "walks toward camera"},
    }
    prompt = build_h3_temporal_prompt({}, shot, duration_sec=10)
    tc_lines = [l for l in prompt.split("\n") if l.strip().startswith("[")]
    assert tc_lines[0].strip().startswith("[0s-")
    assert any("10s]" in l for l in tc_lines)
    check = validate_timeline_coverage(prompt, duration_sec=10)
    assert check["ok"], check


def test_h3_temporal_prompt_5s_has_2_to_3_segments() -> None:
    """~5s clips should have 2-3 segments."""
    shot = {"id": "s5", "dsl": {"action": "wave"}}
    prompt = build_h3_temporal_prompt({}, shot, duration_sec=5)
    segment_count = prompt.count("[")
    assert 2 <= segment_count <= 3


def test_h3_temporal_prompt_15s_has_5_segments() -> None:
    """~15s clips should have 5 segments."""
    shot = {"id": "s15", "dsl": {"action": "walk across room"}}
    prompt = build_h3_temporal_prompt({}, shot, duration_sec=15)
    segment_count = prompt.count("[")
    assert segment_count == 5


def test_h3_temporal_prompt_includes_dialogue() -> None:
    """Dialogue must survive into temporal prompt segments."""
    shot = {
        "id": "s_dlg",
        "dramatic_function": "approach",
        "screen_mode": "on_camera",
        "dsl": {"action": "faces camera"},
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "spoken_text": "等一下。",
            }
        ],
    }
    prompt = build_h3_temporal_prompt({}, shot, duration_sec=8)
    assert "等一下。" in prompt
    assert "lip sync" in prompt.lower()


def test_h3_temporal_prompt_continuity_and_primary_action() -> None:
    """Layer-4: continuity anchors + one primary action language per segment."""
    shot = {
        "id": "s_cont",
        "dramatic_function": "action",
        "heat_phase": "act",
        "dsl": {
            "action": "body rocks with rhythm",
            "motion": "hands re-grip fabric",
            "visible_change": "weight shifts hard",
            "camera_prompt": "handheld push-in",
        },
    }
    prompt = build_h3_temporal_prompt({}, shot, duration_sec=8)
    low = prompt.lower()
    assert "continuity" in low or "same character appearance" in low
    assert "primary action" in low
    assert "environment in motion" in low
    assert "ending pose" in low or "resolves" in low
    assert "camera mode: single continuous" in low


def test_h3_temporal_prompt_5090_path_in_workflow(tmp_path: Path) -> None:
    """_prompt_for_shot uses temporal format when _i2v_profile is h3_primary."""
    spec = {
        "title": "t",
        "_i2v_profile": "h3_primary",
        "director_intent": {"protagonist_want": "靠近他"},
        "h3": {"max_duration_sec": 8},
        "scenes": [
            {
                "id": "sc1",
                "shots": [
                    {
                        "id": "shot_temporal",
                        "shot_role": "hero",
                        "dramatic_function": "approach",
                        "screen_mode": "on_camera",
                        "dsl": {
                            "action": "steps closer",
                            "camera_prompt": "medium close-up",
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
    # Temporal format: must have timecode segments
    assert "[0s-" in prompt
    # Dialogue must survive
    assert "过来。" in prompt
    # Temporal prompt has no provider prefix line (H3 uses 9:16 natively)
    assert "Vertical 9:16" not in prompt


def test_h3_temporal_prompt_hybrid_h3_path_in_workflow(tmp_path: Path) -> None:
    """_prompt_for_shot uses temporal format when _i2v_profile is hybrid_h3."""
    spec = {
        "title": "t",
        "_i2v_profile": "hybrid_h3",
        "h3": {"max_duration_sec": 5},
        "scenes": [
            {
                "id": "sc1",
                "shots": [
                    {
                        "id": "shot_hybrid",
                        "shot_role": "hero",
                        "dramatic_function": "approach",
                        "dsl": {"action": "steps closer"},
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
    assert "[0s-" in prompt


def test_h3_temporal_prompt_non_5090_uses_spine(tmp_path: Path) -> None:
    """_prompt_for_shot uses spine format (with provider prefix) when profile is NOT h3_primary/hybrid_h3."""
    spec = {
        "title": "t",
        "_i2v_profile": "grok_primary",
        "scenes": [
            {
                "id": "sc1",
                "shots": [
                    {
                        "id": "shot_grok",
                        "shot_role": "hero",
                        "dramatic_function": "approach",
                        "dsl": {"action": "steps closer"},
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
    # Spine format: has provider prefix (the key differentiator from temporal path)
    assert "Vertical 9:16" in prompt


def test_build_h3_temporal_prompt_with_ref_images(tmp_path: Path) -> None:
    """When ref_image_paths are provided, the prompt includes the 2V reference stage."""
    from h3_timeline_prompt import inject_2v_reference_stage

    shot = {
        "id": "s1",
        "shot_role": "hero",
        "dramatic_function": "hook",
        "dsl": {"environment": "a dark alley"},
    }
    # Without ref images: no 2V stage marker
    prompt_plain = build_h3_temporal_prompt({}, shot, duration_sec=5)
    assert "=== 2V REFERENCE STAGE ===" not in prompt_plain

    # With ref images: 2V stage marker present
    prompt_with_ref = build_h3_temporal_prompt(
        {}, shot, duration_sec=5, ref_image_paths=["/tmp/ref.png"]
    )
    assert "=== 2V REFERENCE STAGE ===" in prompt_with_ref
    assert "Composition prompt:" in prompt_with_ref
    assert "Generate or refine" in prompt_with_ref
