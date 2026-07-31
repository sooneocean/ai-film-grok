from __future__ import annotations

import json
from pathlib import Path

import pytest
from audio_production import AudioProductionError, prepare_audio_production
from audio_timeline import timeline_hash
from util import read_json, write_json


def test_audio_produce_compiles_every_track_into_one_receipt(tmp_path: Path):
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "audio_timeline_v1": True,
                "audio_style": "audiobook",
                "shots": [
                    {
                        "id": "s1",
                        "duration_sec": 4,
                        "audio_cues": [
                            {
                                "kind": "voice",
                                "line_type": "narration",
                                "speaker": "narrator",
                                "spoken_text": "测试旁白",
                                "start_offset_sec": 0,
                                "duration_sec": 1,
                            },
                            {
                                "kind": "music",
                                "source": "local:bg.wav",
                                "license": "own",
                                "source_sha256": "a" * 64,
                                "start_offset_sec": 0,
                                "duration_sec": 4,
                            },
                            {
                                "kind": "foley",
                                "source": "local:step.wav",
                                "license": "own",
                                "source_sha256": "b" * 64,
                                "start_offset_sec": 1,
                                "duration_sec": 1,
                            },
                            {
                                "kind": "ambience",
                                "source": "local:room.wav",
                                "license": "own",
                                "source_sha256": "c" * 64,
                                "start_offset_sec": 0,
                                "duration_sec": 4,
                            },
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = prepare_audio_production(tmp_path)

    assert Path(report["path"]).is_file()
    assert {name: track["event_count"] for name, track in report["tracks"].items()} == {
        "tts": 1,
        "bgm": 1,
        "foley": 1,
        "ambience": 1,
    }
    assert report["tts"]["ready"] is False
    assert "never generated or approved" in report["candidate_policy"]


def test_audio_produce_requires_a_film_spec(tmp_path: Path):
    with pytest.raises(AudioProductionError, match="film-spec.json"):
        prepare_audio_production(tmp_path)


def test_audio_produce_preserves_matching_rendered_tts_and_measured_duration(tmp_path: Path):
    (tmp_path / "film-spec.json").write_text(
        json.dumps(
            {
                "audio_timeline_v1": True,
                "audio_style": "audiobook",
                "shots": [
                    {
                        "id": "s1",
                        "duration_sec": 2,
                        "audio_cues": [
                            {
                                "kind": "voice",
                                "line_type": "narration",
                                "speaker": "narrator",
                                "spoken_text": "测试旁白",
                                "start_offset_sec": 0,
                                "duration_sec": 1,
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    prepare_audio_production(tmp_path)
    timeline = read_json(tmp_path / "audio" / "audio-timeline.json")
    manifest = read_json(tmp_path / "audio" / "tts-manifest.json")
    event = timeline["events"][0]
    event["duration_sec"] = 0.8
    event["actual_duration_sec"] = 0.8
    manifest["timeline_sha256"] = timeline_hash(timeline)
    manifest["jobs"][0].update(
        {
            "status": "rendered",
            "actual_duration_sec": 0.8,
            "asset_sha256": "a" * 64,
            "tts": {"backend": "edge"},
        }
    )
    write_json(tmp_path / "audio" / "audio-timeline.json", timeline)
    write_json(tmp_path / "audio" / "tts-manifest.json", manifest)

    report = prepare_audio_production(tmp_path)

    restored_timeline = read_json(tmp_path / "audio" / "audio-timeline.json")
    restored_manifest = read_json(tmp_path / "audio" / "tts-manifest.json")
    assert restored_timeline["events"][0]["actual_duration_sec"] == 0.8
    assert restored_manifest["jobs"][0]["status"] == "rendered"
    assert report["tts"]["ready"] is True
