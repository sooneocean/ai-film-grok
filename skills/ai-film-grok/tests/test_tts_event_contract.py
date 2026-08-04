from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audio_timeline import AudioTimelineError, compile_timeline
from voice_cast_profiles import event_language


def test_timeline_blocks_explicit_stage_direction_in_spoken_text():
    with pytest.raises(AudioTimelineError, match="stage direction"):
        compile_timeline(
            {
                "shots": [
                    {
                        "id": "s1",
                        "duration_sec": 2,
                        "audio_cues": [
                            {
                                "kind": "voice",
                                "line_type": "dialogue",
                                "speaker": "hero",
                                "spoken_text": "（镜头切换，脚步声渐近）你来了。",
                                "start_offset_sec": 0,
                                "duration_sec": 1,
                            }
                        ],
                    }
                ]
            }
        )


def test_timeline_allows_spoken_imperative_that_mentions_an_action():
    timeline = compile_timeline(
        {
            "shots": [
                {
                    "id": "s1",
                    "duration_sec": 2,
                    "audio_cues": [
                        {
                            "kind": "voice",
                            "line_type": "dialogue",
                            "speaker": "hero",
                            "spoken_text": "快开门！",
                            "start_offset_sec": 0,
                            "duration_sec": 1,
                        }
                    ],
                }
            ]
        }
    )
    assert timeline["events"][0]["text"] == "快开门！"


def test_timeline_allows_bracketed_dialogue_that_mentions_sound_or_subtitles():
    timeline = compile_timeline(
        {
            "shots": [
                {
                    "id": "s1",
                    "duration_sec": 2,
                    "audio_cues": [
                        {
                            "kind": "voice",
                            "line_type": "dialogue",
                            "speaker": "hero",
                            "spoken_text": "（脚步声太大了）我睡不着。",
                            "start_offset_sec": 0,
                            "duration_sec": 1,
                        }
                    ],
                }
            ]
        }
    )
    assert timeline["events"][0]["text"] == "（脚步声太大了）我睡不着。"


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        # Chinese-only product (2026-08-04): all vocal types resolve to zh.
        ({"type": "dialogue", "speaker": "hero"}, "zh"),
        ({"type": "inner_voice", "speaker": "hero"}, "zh"),
        ({"type": "media_voice", "speaker": "hero"}, "zh"),
        ({"type": "dialogue", "speaker": "hero", "language": "zh"}, "zh"),
        ({"type": "inner_voice", "speaker": "hero", "spoken_lang": "zh"}, "zh"),
        ({"type": "narration", "speaker": "narrator"}, "zh"),
        ({"type": "media_voice", "speaker": "broadcast"}, "zh"),
    ],
)
def test_event_language_keeps_character_voice_language_across_carriers(event, expected):
    assert event_language(event) == expected


def test_event_language_rejects_japanese():
    import pytest
    from voice_cast_profiles import VoiceCastError

    with pytest.raises(VoiceCastError, match="retired"):
        event_language({"type": "dialogue", "speaker": "hero", "language": "ja"})
