from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from film_spec import FilmSpecError, _validate_dialogue_drama_shot  # noqa: E402


def _on_camera_shot() -> dict:
    return {
        "screen_mode": "on_camera",
        "dialogue_line_id": "sc02_ln07",
        "speaker": "heroine",
        "speaker_on_camera": True,
        "lipsync": True,
        "lipsync_required": True,
        "performance_state_id": "heroine-sc02-door",
        "translation_status": "ready",
        "dialogue_ja": "行く。",
        "caption_text": "我要走了。",
        "performance_state": {"head_angle": "three-quarter"},
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "speaker": "heroine",
                "spoken_text": "行く。",
                "language": "ja",
                "duration_sec": 1,
            }
        ],
        "dsl": {"camera": {"shot_size": "close-up"}},
    }


def test_on_camera_requires_short_near_state_locked_performance() -> None:
    shot = _on_camera_shot()
    _validate_dialogue_drama_shot(shot, shot_id="talk01")

    shot["audio_cues"][0]["spoken_text"] = "あ" * 43
    with pytest.raises(FilmSpecError, match="exceeds"):
        _validate_dialogue_drama_shot(shot, shot_id="talk01")

    shot = _on_camera_shot()
    shot["dsl"]["camera"]["shot_size"] = "wide"
    with pytest.raises(FilmSpecError, match="near framing"):
        _validate_dialogue_drama_shot(shot, shot_id="talk01")


def _narration_shot() -> dict:
    return {
        "id": "gap01",
        "screen_mode": "action_cover",
        "narration_reason": "time jump",
        "audio_cues": [
            {
                "kind": "voice",
                "line_type": "narration",
                "spoken_text": "三天后，她回到车站。",
                "start_offset_sec": 0,
                "duration_sec": 2,
            }
        ],
        "must_show": "她推开车站的门",
        "visible_change": "门从关闭到打开",
        "dsl": {"action": "she opens the station door"},
    }


def test_strict_gap_narration_requires_reasoned_uncovered_information() -> None:
    shot = _narration_shot()
    with pytest.raises(FilmSpecError, match="narration_gap evidence"):
        _validate_dialogue_drama_shot(
            shot,
            shot_id="gap01",
            narration_gap_strict=True,
        )

    shot["narration_gap"] = {
        "gap_id": "gap_01",
        "reason": "time_jump",
        "uncovered_information": "three days elapsed off screen",
        "source_refs": ["source:paragraph-4"],
    }
    _validate_dialogue_drama_shot(
        shot,
        shot_id="gap01",
        narration_gap_strict=True,
    )


def test_strict_gap_narration_rejects_visual_duplication() -> None:
    shot = _narration_shot()
    shot["audio_cues"][0]["spoken_text"] = "门从关闭到打开"
    shot["narration_gap"] = {
        "gap_id": "gap_01",
        "reason": "offscreen_fact",
        "uncovered_information": "door movement",
    }
    with pytest.raises(FilmSpecError, match="duplicates visible information"):
        _validate_dialogue_drama_shot(
            shot,
            shot_id="gap01",
            narration_gap_strict=True,
        )


def test_narrative_gap_narration_requires_a_real_gap() -> None:
    shot = _narration_shot()
    shot["audio_cues"][0]["duration_sec"] = 1.2
    shot["narration_gap"] = {
        "gap_id": "gap_01",
        "reason": "narrative_gap",
        "uncovered_information": "an offscreen decision happened",
    }
    with pytest.raises(FilmSpecError, match="more than 1.2"):
        _validate_dialogue_drama_shot(
            shot,
            shot_id="gap01",
            narration_gap_strict=True,
        )
