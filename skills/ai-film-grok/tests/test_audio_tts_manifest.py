from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from audio_timeline import compile_timeline
from audio_tts_manifest import AudioTTSManifestError, apply_measured_durations, build_tts_manifest
from voice_cast_profiles import assign_profiles


def _timeline():
    return compile_timeline(
        {
            "audio_style": "drama_radio",
            "shots": [
                {
                    "id": "s1",
                    "duration_sec": 3,
                    "audio_cues": [
                        {
                            "kind": "voice",
                            "line_type": "dialogue",
                            "speaker": "hero",
                            "spoken_text": "走吧",
                            "language": "zh",
                            "start_offset_sec": 0,
                            "duration_sec": 1,
                        },
                        {
                            "kind": "sfx",
                            "asset_hint": "door",
                            "source": "local:assets/door.wav",
                            "license": "owned",
                            "source_sha256": "a" * 64,
                            "start_offset_sec": 1,
                            "duration_sec": 1,
                        },
                    ],
                }
            ],
        }
    )


def _cast():
    return {"profiles": assign_profiles([{"speaker_id": "hero", "language": "zh"}])}


def test_manifest_contains_one_provenanced_job_per_vocal_event():
    manifest = build_tts_manifest(_timeline(), _cast())

    assert len(manifest["jobs"]) == 1
    job = manifest["jobs"][0]
    assert job["language"] == "zh"
    assert job["asset_path"].endswith(".wav")
    assert len(job["request_sha256"]) == 64


def test_measured_duration_cannot_exceed_reserved_event_window():
    timeline = _timeline()
    with pytest.raises(AudioTTSManifestError, match="exceeds reserved window"):
        apply_measured_durations(timeline, {timeline["events"][0]["id"]: 1.2})


def test_measured_duration_is_written_back_as_auditable_actual_duration():
    timeline = _timeline()
    event_id = timeline["events"][0]["id"]

    updated = apply_measured_durations(timeline, {event_id: 0.8})

    assert updated["events"][0]["actual_duration_sec"] == 0.8
    assert updated["events"][0]["duration_sec"] == 0.8
