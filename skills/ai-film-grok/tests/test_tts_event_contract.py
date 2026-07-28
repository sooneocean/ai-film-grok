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


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ({"type": "dialogue", "speaker": "hero"}, "ja"),
        ({"type": "inner_voice", "speaker": "hero"}, "ja"),
        ({"type": "media_voice", "speaker": "hero"}, "ja"),
        ({"type": "narration", "speaker": "narrator"}, "zh"),
        ({"type": "media_voice", "speaker": "broadcast"}, "zh"),
    ],
)
def test_event_language_keeps_character_voice_language_across_carriers(event, expected):
    assert event_language(event) == expected
