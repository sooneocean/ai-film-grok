"""v2.34 dialogue-first: scene-level no-dialogue rejection + H3 dialogue prompt."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from film_spec import FilmSpecError, validate_film_spec  # noqa: E402
from h3_workflow import _prompt_for_shot  # noqa: E402


def _base_spec(*, scenes: list) -> dict:
    return {
        "schema_version": 1,
        "title": "t",
        "vo_mode": "dialogue_drama",
        "dialogue_spoken_lang": "zh",
        "narration_spoken_lang": "zh",
        "aspect": "9:16",
        "heat_scale": "soft",
        "director_intent": {
            "logline": "Her voice carries every scene; narration never speaks for her.",
            "tone": "drama",
            "emotional_arc": ["a", "b", "c"],
        },
        "transition_sec": 0.25,
        "transition_default": "soft",
        "scenes": scenes,
    }


def _dialogue_shot(sid: str, text: str, beat: str) -> dict:
    return {
        "id": sid,
        "dramatic_function": "action",
        "duration_sec": 8,
        "screen_mode": "on_camera",
        "speaker": "hero",
        "dialogue_line_id": f"ln_{sid}",
        "performance_state_id": f"st_{sid}",
        "lipsync_required": True,
        "speaker_on_camera": True,
        "lipsync": True,
        "beat_id": beat,
        "caption_text": text,
        "nar": text,
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "language": "zh",
                "speaker": "hero",
                "spoken_text": text,
                "duration_sec": 8,
            }
        ],
        "performance_state": {"head_angle": "front"},
        "dsl": {
            "subject": "woman",
            "action": "speak close-up",
            "motion": "lips move eyes blink",
            "camera": {"shot_size": "close-up"},
        },
    }


def _action_cover_shot(sid: str, beat: str) -> dict:
    return {
        "id": sid,
        "dramatic_function": "action",
        "duration_sec": 3,
        "screen_mode": "action_cover",
        "beat_id": beat,
        # no nar — storyteller gate forbids bare nar without matching narration voice cue
        "audio_cues": [
            {"kind": "silence", "start_offset_sec": 0, "duration_sec": 3}
        ],
        "dsl": {
            "subject": "her hand",
            "action": "fingers trail along fabric",
            "motion": "hand glides slowly",
            "camera": {"shot_size": "medium"},
        },
    }


def _silence_shot(sid: str) -> dict:
    return {
        "id": sid,
        "dramatic_function": "bridge",
        "duration_sec": 8,
        # silence shots cannot legally carry nar under dialogue_drama storyteller gate.
        # Use action_cover instead when a narration bridge is genuinely required.
        "screen_mode": "silence",
        "caption_text": "",
        # NOTE: "nar" omitted entirely — in dialogue_drama a silence shot has no voice cue
        # and any non-empty nar would trip the third-person storyteller gate. Omit nar so
        # validate_nar_budget is skipped and est_vo_sec is zeroed.
        "audio_cues": [
            {"kind": "silence", "start_offset_sec": 0, "duration_sec": 2}
        ],
        "dsl": {
            "subject": "rain on window",
            "action": "rain streaks the glass",
            "motion": "rain falls camera holds",
            "camera": {"shot_size": "wide"},
        },
    }


def test_scene_with_only_action_cover_is_rejected() -> None:
    spec = _base_spec(
        scenes=[
            {
                "id": "sc1",
                "shots": [_action_cover_shot("shot01", beat="b1")],
            }
        ]
    )
    with pytest.raises(
        FilmSpecError,
        match="requires dialogue in every scene",
    ):
        validate_film_spec(spec, assign_missing_ids=False)


def test_scene_with_only_silence_is_rejected() -> None:
    spec = _base_spec(scenes=[{"id": "sc1", "shots": [_silence_shot("shot01")]}])
    with pytest.raises(
        FilmSpecError,
        match="requires dialogue in every scene",
    ):
        validate_film_spec(spec, assign_missing_ids=False)


def test_scene_with_on_camera_dialogue_passes() -> None:
    spec = _base_spec(
        scenes=[
            {
                "id": "sc1",
                "shots": [
                    _dialogue_shot("shot01", "别走。", beat="b1"),
                    # reaction coverage for beat b1 is mandatory under dialogue_drama
                    {
                        "id": "shot02",
                        "dramatic_function": "reaction",
                        "duration_sec": 2,
                        "screen_mode": "reaction",
                        "beat_id": "b1",
                        "audio_cues": [
                            {"kind": "silence", "start_offset_sec": 0, "duration_sec": 2}
                        ],
                        "dsl": {
                            "subject": "hero",
                            "action": "eyes lift",
                            "motion": "slow eyebrow lift",
                            "camera": {"shot_size": "close-up"},
                        },
                    },
                ],
            }
        ]
    )
    validate_film_spec(spec, assign_missing_ids=False)
    assert spec["_dialogue_drama"]["scenes_without_dialogue"] == []
    assert spec["_dialogue_drama"]["allow_silent_scenes"] is False


def test_scene_with_silent_scene_and_reason_passes() -> None:
    scene = {
        "id": "sc_gap",
        "silent_scene": True,
        "narration_reason": "time_jump gap between chapters, no character on camera",
        "shots": [_silence_shot("shot01")],
    }
    spec = _base_spec(scenes=[scene])
    validate_film_spec(spec, assign_missing_ids=False)


def test_scene_marked_silent_without_reason_is_rejected() -> None:
    spec = _base_spec(
        scenes=[{"id": "sc1", "silent_scene": True, "shots": [_silence_shot("shot01")]}]
    )
    with pytest.raises(
        FilmSpecError,
        match="requires dialogue in every scene",
    ):
        validate_film_spec(spec, assign_missing_ids=False)


def test_silent_scene_opt_out_via_allow_silent_scenes() -> None:
    spec = _base_spec(scenes=[{"id": "sc1", "shots": [_silence_shot("shot01")]}])
    spec["allow_silent_scenes"] = True
    validate_film_spec(spec, assign_missing_ids=False)
    assert spec["_dialogue_drama"]["allow_silent_scenes"] is True


# H3 dialogue prompt injection


def test_h3_prompt_injects_dialogue_for_on_camera_shot(tmp_path: Path) -> None:
    root = tmp_path
    shot = {
        "id": "shot01",
        "screen_mode": "on_camera",
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "spoken_text": "别走。",
                "language": "zh",
                "speaker": "hero",
            }
        ],
        "dsl": {"action": "speak close-up", "motion": "lips move"},
    }
    prompt = _prompt_for_shot(root, shot, mode="i2v")
    assert "speaks this line in natural Mandarin on camera" in prompt
    assert "别走。" in prompt
    assert "lip sync priority" in prompt
    # ambient fallback not used when dialogue is present
    assert "no on-screen speech unless the shot is clearly dialogue" not in prompt


def test_h3_prompt_ambience_when_no_dialogue(tmp_path: Path) -> None:
    root = tmp_path
    shot = {
        "id": "shot02",
        "screen_mode": "action_cover",
        "audio_cues": [{"kind": "silence", "start_offset_sec": 0, "duration_sec": 2}],
        "dsl": {"action": "walk in", "motion": "steps"},
    }
    prompt = _prompt_for_shot(root, shot, mode="i2v")
    assert "no on-screen speech unless the shot is clearly dialogue" in prompt
    assert "mandarin on camera" not in prompt


def test_h3_prompt_off_camera_dialogue_uses_off_camera_wording(tmp_path: Path) -> None:
    root = tmp_path
    shot = {
        "id": "shot03",
        "screen_mode": "off_camera",
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "spoken_text": "别走。",
                "language": "zh",
                "speaker": "hero",
            }
        ],
        "dsl": {"action": "speak off-screen", "motion": "rain behind"},
    }
    prompt = _prompt_for_shot(root, shot, mode="i2v")
    assert "off camera" in prompt
    assert "别走。" in prompt


def test_h3_r2v_prefix_pairs_with_dialogue(tmp_path: Path) -> None:
    root = tmp_path
    shot = {
        "id": "shot04",
        "screen_mode": "on_camera",
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "spoken_text": "我到了。",
                "language": "zh",
                "speaker": "hero",
            }
        ],
        "dsl": {"action": "speak", "motion": "lips move"},
    }
    prompt = _prompt_for_shot(root, shot, mode="r2v")
    assert "<Picture 1>" in prompt
    assert "我到了。" in prompt


def test_h3_prompt_file_still_injects_dialogue(tmp_path: Path) -> None:
    """Custom receipts/prompts/*.i2v.txt must not kill Mandarin inject (2026-08-04)."""
    root = tmp_path
    (root / "receipts" / "prompts").mkdir(parents=True)
    (root / "receipts" / "prompts" / "shot05.i2v.txt").write_text(
        "Vertical 9:16 close-up. Keep identity. Soft push-in.\n",
        encoding="utf-8",
    )
    shot = {
        "id": "shot05",
        "screen_mode": "on_camera",
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "spoken_text": "过来，靠近一点。",
                "language": "zh",
                "speaker": "hero",
            }
        ],
    }
    prompt = _prompt_for_shot(root, shot, mode="i2v")
    assert "Keep identity" in prompt
    assert "过来，靠近一点。" in prompt
    assert "lip sync priority" in prompt


def test_h3_prompt_file_with_audio_block_still_gets_missing_line(tmp_path: Path) -> None:
    root = tmp_path
    (root / "receipts" / "prompts").mkdir(parents=True)
    (root / "receipts" / "prompts" / "shot06.i2v.txt").write_text(
        "Vertical 9:16. Keep identity. Audio: quiet room tone; no speech.\n",
        encoding="utf-8",
    )
    shot = {
        "id": "shot06",
        "screen_mode": "on_camera",
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "spoken_text": "看着我。",
                "language": "zh",
                "speaker": "hero",
            }
        ],
    }
    prompt = _prompt_for_shot(root, shot, mode="i2v")
    assert "看着我。" in prompt
    assert "lip sync priority" in prompt
