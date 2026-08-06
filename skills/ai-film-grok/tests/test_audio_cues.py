from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from audio_cues import (
    AudioCueError,
    compile_audio_timeline,
    primary_voice_cue,
    strict_tts_text,
    validate_audio_cues,
)
from render_final import build_subtitle_cues_for_shots


def _shot(cues: list[dict], *, duration: float = 5.0) -> dict:
    return {"id": "shot01", "duration_sec": duration, "audio_cues": cues}


def test_voice_text_is_separate_from_foley_and_compiles_to_absolute_time():
    shot = _shot(
        [
            {
                "kind": "voice",
                "speaker": "heroine",
                "line_type": "dialogue",
                "spoken_text": "别回头。",
                "emotion": "fear",
                "performance": {"rate": 0.8},
                "start_offset_sec": 1.2,
                "duration_sec": 1.4,
            },
            {
                "kind": "foley",
                "asset_hint": "wet_footsteps",
                "start_offset_sec": 0.1,
                "duration_sec": 0.8,
            },
            {
                "kind": "silence",
                "purpose": "hear the door",
                "start_offset_sec": 3.0,
                "duration_sec": 0.6,
            },
        ]
    )
    report = validate_audio_cues([shot], strict=False)
    assert report["voice_cues"] == 1
    timeline = compile_audio_timeline([shot], shot_starts={"shot01": 4.0})
    assert timeline[0]["start_sec"] == 5.2
    assert timeline[1]["asset_hint"] == "wet_footsteps"
    assert "spoken_text" not in timeline[1]


def test_non_voice_text_never_enters_tts_contract():
    with pytest.raises(AudioCueError, match="only allowed on voice"):
        validate_audio_cues(
            [
                _shot(
                    [
                        {
                            "kind": "sfx",
                            "spoken_text": "脚步声",
                            "asset_hint": "footsteps",
                            "start_offset_sec": 0,
                            "duration_sec": 1,
                        }
                    ]
                )
            ],
            strict=True,
        )


def test_strict_mode_never_falls_back_to_legacy_narration_or_stage_directions():
    with pytest.raises(AudioCueError, match="require a voice cue"):
        strict_tts_text({"id": "shot01", "nar": "脚步声"}, strict=True)
    with pytest.raises(AudioCueError, match="sound/action direction"):
        validate_audio_cues(
            [
                _shot(
                    [
                        {
                            "kind": "voice",
                            "speaker": "narrator",
                            "line_type": "narration",
                            "spoken_text": "（脚步声）快走",
                            "start_offset_sec": 0,
                            "duration_sec": 1,
                        }
                    ]
                )
            ],
            strict=True,
        )


def test_strict_mode_rejects_empty_cue_list():
    with pytest.raises(AudioCueError, match="cannot be empty"):
        validate_audio_cues([_shot([])], strict=True)


def test_voice_must_fit_its_shot_and_only_one_turn_is_renderable():
    with pytest.raises(AudioCueError, match="exceeds"):
        validate_audio_cues(
            [
                _shot(
                    [
                        {
                            "kind": "voice",
                            "speaker": "narrator",
                            "line_type": "narration",
                            "spoken_text": "一段话",
                            "start_offset_sec": 4.5,
                            "duration_sec": 1,
                        }
                    ]
                )
            ],
            strict=True,
        )
    shot = _shot(
        [
            {
                "kind": "voice",
                "speaker": "a",
                "line_type": "dialogue",
                "spoken_text": "甲",
                "start_offset_sec": 0,
                "duration_sec": 1,
            },
            {
                "kind": "voice",
                "speaker": "b",
                "line_type": "dialogue",
                "spoken_text": "乙",
                "start_offset_sec": 2,
                "duration_sec": 1,
            },
        ]
    )
    validate_audio_cues([shot], strict=False)
    with pytest.raises(AudioCueError, match="split multiple"):
        primary_voice_cue(shot)


def test_caption_starts_with_the_timed_voice_not_the_shot():
    cues, _ = build_subtitle_cues_for_shots(
        [{"target": 5.0, "raw_vo_dur": 1.0, "voice_start_offset_sec": 1.2, "units": ["别回头"]}],
        title_duration=0.0,
        end_duration=0.0,
        transition_sec=0.0,
    )
    assert cues[0]["start"] >= 1.2
