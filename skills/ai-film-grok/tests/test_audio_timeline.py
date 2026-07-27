from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from audio_plan import build_audio_plan
from audio_timeline import (
    AudioTimelineError,
    build_mix_execution_plan,
    caption_bindings,
    compile_timeline,
)
from voice_cast_profiles import VoiceCastError, assign_profiles, validate_event_language


def _spec(cues, *, mode="drama_radio"):
    return {"audio_style": mode, "shots": [{"id": "s1", "duration_sec": 4, "audio_cues": cues}]}


def test_eight_types_are_compiled_and_non_voice_never_carries_tts_text():
    cues = [
        {
            "kind": "voice",
            "line_type": "dialogue",
            "speaker": "hero",
            "spoken_text": "行こう。",
            "start_offset_sec": 0,
            "duration_sec": 1,
        },
        {
            "kind": "voice",
            "line_type": "inner_monologue",
            "speaker": "hero",
            "spoken_text": "不能回头",
            "start_offset_sec": 1,
            "duration_sec": 1,
        },
        {
            "kind": "voice",
            "line_type": "phone_broadcast",
            "speaker": "radio",
            "spoken_text": "警报",
            "start_offset_sec": 2,
            "duration_sec": 1,
        },
        {
            "kind": "foley",
            "asset_hint": "door",
            "source": "local:door.wav",
            "license": "own",
            "source_sha256": "a" * 64,
            "start_offset_sec": 0,
            "duration_sec": 1,
        },
        {
            "kind": "ambience",
            "asset_hint": "rain",
            "source": "https://example.test/rain.wav",
            "license": "cc0",
            "source_sha256": "b" * 64,
            "start_offset_sec": 0,
            "duration_sec": 4,
        },
        {
            "kind": "music",
            "asset_hint": "bed",
            "source": "local:bed.wav",
            "license": "own",
            "source_sha256": "c" * 64,
            "start_offset_sec": 0,
            "duration_sec": 4,
        },
        {"kind": "silence", "start_offset_sec": 3, "duration_sec": 0.5},
    ]
    timeline = compile_timeline(_spec(cues))
    assert {event["type"] for event in timeline["events"]} == {
        "dialogue",
        "inner_voice",
        "media_voice",
        "action_sfx",
        "ambience",
        "music",
        "silence",
    }
    assert all("text" not in event for event in timeline["events"] if event["type"] == "action_sfx")


def test_vocal_overlap_requires_explicit_policy():
    cues = [
        {
            "kind": "voice",
            "line_type": "dialogue",
            "speaker": "a",
            "spoken_text": "あ",
            "start_offset_sec": 0,
            "duration_sec": 2,
        },
        {
            "kind": "voice",
            "line_type": "dialogue",
            "speaker": "b",
            "spoken_text": "い",
            "start_offset_sec": 1,
            "duration_sec": 2,
        },
    ]
    with pytest.raises(AudioTimelineError, match="requires interrupt"):
        compile_timeline(_spec(cues))
    cues[1]["overlap_policy"] = "cross_talk"
    assert compile_timeline(_spec(cues))["events"][1]["overlap_policy"] == "cross_talk"


def test_style_rules_and_caption_bindings_are_event_bound():
    with pytest.raises(AudioTimelineError, match="forbids narration"):
        compile_timeline(
            _spec(
                [
                    {
                        "kind": "voice",
                        "line_type": "narration",
                        "speaker": "narrator",
                        "spoken_text": "旁白",
                        "start_offset_sec": 0,
                        "duration_sec": 1,
                    }
                ],
                mode="immersive_theatre",
            )
        )
    timeline = compile_timeline(
        _spec(
            [
                {
                    "kind": "voice",
                    "line_type": "dialogue",
                    "speaker": "hero",
                    "spoken_text": "行こう",
                    "caption_text": "走吧",
                    "start_offset_sec": 0,
                    "duration_sec": 1,
                }
            ]
        )
    )
    bound = caption_bindings(timeline)
    assert bound[0]["audio_event_id"] == timeline["events"][0]["id"]
    assert bound[0]["caption_text"] == "走吧"


def test_stable_voice_profiles_respect_locks_and_language():
    first = assign_profiles(
        [{"speaker_id": "hero", "language": "ja"}, {"speaker_id": "narrator", "language": "zh"}]
    )
    again = assign_profiles([{"speaker_id": "hero", "language": "ja"}], first)
    assert first["hero"]["voice_id"] == again["hero"]["voice_id"]
    validate_event_language({"id": "x", "type": "dialogue"}, first["hero"])
    with pytest.raises(VoiceCastError, match="requires ja"):
        validate_event_language({"id": "x", "type": "dialogue"}, first["narrator"])


def test_asset_requires_hash_and_license_in_v1():
    with pytest.raises(AudioTimelineError, match="source_sha256"):
        compile_timeline(
            _spec(
                [
                    {
                        "kind": "sfx",
                        "asset_hint": "door",
                        "source": "local:door.wav",
                        "license": "own",
                        "start_offset_sec": 0,
                        "duration_sec": 1,
                    }
                ]
            )
        )


def test_mix_plan_has_inner_voice_filter_event_pan_fades_and_all_vocal_ducking():
    timeline = compile_timeline(
        _spec(
            [
                {
                    "kind": "voice",
                    "line_type": "inner_monologue",
                    "speaker": "hero",
                    "spoken_text": "不能回头",
                    "start_offset_sec": 1,
                    "duration_sec": 2,
                    "pan": -0.5,
                    "fade_in_sec": 0.2,
                    "fade_out_sec": 0.3,
                },
                {
                    "kind": "voice",
                    "line_type": "dialogue",
                    "speaker": "heroine",
                    "spoken_text": "快走",
                    "start_offset_sec": 3,
                    "duration_sec": 1,
                },
            ]
        )
    )
    plan = build_mix_execution_plan(timeline)
    first = plan["lanes"][0]
    assert plan["sample_rate"] == 48000
    assert "highpass=f=250,lowpass=f=3200" in first["filters"]
    assert any(item.startswith("pan=stereo") for item in first["filters"])
    assert plan["ducking"]["trigger_event_ids"] == [event["id"] for event in timeline["events"]]


def test_audio_plan_writes_timeline_and_deterministic_voice_cast(tmp_path: Path):
    spec = _spec(
        [
            {
                "kind": "voice",
                "line_type": "dialogue",
                "speaker": "hero",
                "spoken_text": "行こう",
                "start_offset_sec": 0,
                "duration_sec": 1,
            }
        ]
    )
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    report = build_audio_plan(
        tmp_path, compile_timeline=True, write_timeline=True, write_voice_cast=True
    )
    assert report["audio_timeline"]["event_count"] == 1
    assert (tmp_path / "audio" / "audio-timeline.json").is_file()
    profile = report["voice_cast"]["profiles"]["hero"]
    assert profile["language"] == "ja"
    assert profile["voice_id"].startswith("ja-JP-")
