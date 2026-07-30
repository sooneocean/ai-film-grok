from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from audio_timeline import compile_timeline
from performance_candidates import sign_receipt
from scene_sound import reconcile
from scene_sound_stems import SceneSoundError, _apply_event_controls, render_scene_sound_stem


def test_scene_stem_honors_event_pan_gain_and_fades():
    source = np.ones((10, 2), dtype=np.float32)
    out = _apply_event_controls(
        source,
        {"gain": 0.8, "pan": -0.5, "fade_in_sec": 0.2, "fade_out_sec": 0.2},
        10,
    )
    # Fade starts/ends silent; left receives more energy for a left pan.
    assert np.allclose(out[0], 0.0)
    assert np.allclose(out[-1], 0.0)
    assert out[5, 0] > out[5, 1]


def test_scene_stem_accepts_legacy_local_asset_field(tmp_path: Path):
    asset = tmp_path / "assets" / "tone.wav"
    asset.parent.mkdir()
    with wave.open(str(asset), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 800)
    result = render_scene_sound_stem(
        tmp_path,
        {
            "events": [
                {
                    "id": "a",
                    "type": "ambience",
                    "asset": "local:assets/tone.wav",
                    "source_sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
                    "start_sec": 0,
                    "duration_sec": 0.1,
                }
            ]
        },
        duration_sec=1,
        out=tmp_path / "audio" / "scene.wav",
        sample_rate=8000,
    )
    assert Path(result["path"]).is_file()
    assert result["sha256"] == hashlib.sha256(Path(result["path"]).read_bytes()).hexdigest()


def test_scene_stem_rejects_pending_noncommercial_sfx(tmp_path: Path):
    asset = tmp_path / "audio" / "candidates" / "sfx" / "pending" / "take.wav"
    asset.parent.mkdir(parents=True)
    with wave.open(str(asset), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 800)
    with pytest.raises(SceneSoundError, match="cannot enter a formal stem"):
        render_scene_sound_stem(
            tmp_path,
            {
                "events": [
                    {
                        "id": "pending-sfx",
                        "type": "action_sfx",
                        "source": "local:audio/candidates/sfx/pending/take.wav",
                        "license": "CC-BY-NC-4.0",
                        "source_sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
                        "approval_status": "pending_human_review",
                        "production_eligible": False,
                        "start_sec": 0,
                        "duration_sec": 0.1,
                    }
                ]
            },
            duration_sec=1,
            out=tmp_path / "audio" / "scene.wav",
            sample_rate=8000,
        )


def test_scene_stem_accepts_signed_human_approved_internal_sfx(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    approved = tmp_path / "audio" / "candidates" / "sfx" / "approved-noncommercial"
    approved.mkdir(parents=True)
    asset = approved / "take.wav"
    with wave.open(str(asset), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 800)
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    screen_path = tmp_path / "receipts" / "sfx-speech-screen" / "mmaudio-sfx-1-test.json"
    screen_path.parent.mkdir(parents=True)
    screen = {
        "kind": "vibevoice-asr-review",
        "status": "candidate_only",
        "human_review_required": True,
        "provider": {"transcript_sha256": "d" * 64},
        "inputs": {"audio": {"sha256": digest}},
        "transcript": {"segments": [{"text": "[silence]"}]},
    }
    screen_path.write_text(json.dumps(screen), encoding="utf-8")
    record = {
        "schema": "aifilm-sfx-candidate-v1",
        "asset_id": "mmaudio-sfx-1-test",
        "status": "approved_noncommercial",
        "production_eligible": False,
        "usage_scope": "noncommercial_internal_research",
        "delivery_eligible_scopes": ["noncommercial_internal"],
        "approved_path": str(asset.relative_to(tmp_path)),
        "sha256": digest,
        "license": "CC-BY-NC-4.0",
        "model": "hkchengrex/MMAudio-large-44k-v2",
        "checkpoint_fingerprint": "a" * 64,
        "node_job_id": "job-1",
        "asr_speech_screen": {
            "status": "completed_candidate_signal",
            "receipt": f"local:{screen_path.relative_to(tmp_path)}",
            "audio_sha256": digest,
            "report_sha256": hashlib.sha256(screen_path.read_bytes()).hexdigest(),
            "transcript_sha256": "d" * 64,
            "segment_count": 1,
            "speech_like_segment_count": 0,
        },
        "human_review": {
            "reviewer": "dex",
            "heard_full": True,
            "sync_confirmed": True,
            "no_speech_confirmed": True,
            "no_music_confirmed": True,
            "artifact_free_confirmed": True,
            "asr_speech_reviewed": True,
        },
    }
    sign_receipt(record)
    receipt = approved / "take.receipt.json"
    receipt.write_text(json.dumps(record), encoding="utf-8")
    result = render_scene_sound_stem(
        tmp_path,
        {
            "delivery_scope": "noncommercial_internal",
            "events": [
                {
                    "id": "approved-sfx",
                    "type": "action_sfx",
                    "source": f"local:{asset.relative_to(tmp_path)}",
                    "license": record["license"],
                    "source_sha256": digest,
                    "approval_status": "approved_noncommercial",
                    "approval_receipt": f"local:{receipt.relative_to(tmp_path)}",
                    "production_eligible": False,
                    "usage_scope": "noncommercial_internal",
                    "model": record["model"],
                    "checkpoint_fingerprint": record["checkpoint_fingerprint"],
                    "node_job_id": record["node_job_id"],
                    "start_sec": 0,
                    "duration_sec": 0.1,
                }
            ],
        },
        duration_sec=1,
        out=tmp_path / "audio" / "scene-approved.wav",
        sample_rate=8000,
    )
    assert result["event_count"] == 1

    bypass = dict(record)
    bypass.pop("asr_speech_screen")
    bypass["human_review"] = dict(record["human_review"])
    bypass["human_review"].pop("asr_speech_reviewed")
    sign_receipt(bypass)
    receipt.write_text(json.dumps(bypass), encoding="utf-8")
    with pytest.raises(SceneSoundError, match="non-commercial or pending"):
        render_scene_sound_stem(
            tmp_path,
            {
                "delivery_scope": "noncommercial_internal",
                "events": [
                    {
                        "id": "missing-asr-screen",
                        "type": "action_sfx",
                        "source": f"local:{asset.relative_to(tmp_path)}",
                        "license": bypass["license"],
                        "source_sha256": digest,
                        "approval_status": "approved_noncommercial",
                        "approval_receipt": f"local:{receipt.relative_to(tmp_path)}",
                        "production_eligible": False,
                        "usage_scope": "noncommercial_internal",
                        "model": bypass["model"],
                        "checkpoint_fingerprint": bypass["checkpoint_fingerprint"],
                        "node_job_id": bypass["node_job_id"],
                        "start_sec": 0,
                        "duration_sec": 0.1,
                    }
                ],
            },
            duration_sec=1,
            out=tmp_path / "audio" / "scene-missing-asr.wav",
            sample_rate=8000,
        )
    receipt.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(SceneSoundError, match="cannot enter a formal stem"):
        render_scene_sound_stem(
            tmp_path,
            {
                "delivery_scope": "commercial",
                "events": [
                    {
                        "id": "approved-sfx",
                        "type": "action_sfx",
                        "source": f"local:{asset.relative_to(tmp_path)}",
                        "license": record["license"],
                        "source_sha256": digest,
                        "approval_status": "approved_noncommercial",
                        "approval_receipt": f"local:{receipt.relative_to(tmp_path)}",
                        "production_eligible": False,
                        "usage_scope": "noncommercial_internal",
                        "model": record["model"],
                        "checkpoint_fingerprint": record["checkpoint_fingerprint"],
                        "node_job_id": record["node_job_id"],
                        "start_sec": 0,
                        "duration_sec": 0.1,
                    }
                ],
            },
            duration_sec=1,
            out=tmp_path / "audio" / "scene-commercial.wav",
            sample_rate=8000,
        )


@pytest.mark.parametrize(
    "license_id",
    (
        "CC-BY-NC-4.0",
        "CC BY-NC 4.0",
        "CC_BY_NC_4.0",
        "Creative Commons CC BY-NC 4.0",
    ),
)
def test_scene_stem_rejects_nc_license_family(tmp_path: Path, license_id: str):
    asset = tmp_path / "audio" / "imports" / "take.wav"
    asset.parent.mkdir(parents=True)
    with wave.open(str(asset), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 800)

    with pytest.raises(SceneSoundError, match="cannot enter a formal stem"):
        render_scene_sound_stem(
            tmp_path,
            {
                "events": [
                    {
                        "id": "nc-sfx",
                        "type": "action_sfx",
                        "source": "local:audio/imports/take.wav",
                        "license": license_id,
                        "source_sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
                        "start_sec": 0,
                        "duration_sec": 0.1,
                    }
                ]
            },
            duration_sec=1,
            out=tmp_path / "audio" / "scene-nc.wav",
            sample_rate=8000,
        )


def test_scene_stem_rejects_copied_pending_sfx_by_hash(tmp_path: Path):
    pending = tmp_path / "audio" / "candidates" / "sfx" / "pending"
    pending.mkdir(parents=True)
    original = pending / "take.wav"
    with wave.open(str(original), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 800)
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    (pending / "take.json").write_text(
        json.dumps(
            {
                "schema": "aifilm-sfx-candidate-v1",
                "status": "pending_human_review",
                "production_eligible": False,
                "license": "CC-BY-NC-4.0",
                "sha256": digest,
            }
        )
    )

    copied = tmp_path / "audio" / "imports" / "copied.wav"
    copied.parent.mkdir()
    copied.write_bytes(original.read_bytes())

    with pytest.raises(SceneSoundError, match="known non-production SFX hash"):
        render_scene_sound_stem(
            tmp_path,
            {
                "events": [
                    {
                        "id": "renamed-sfx",
                        "type": "action_sfx",
                        "source": "local:audio/imports/copied.wav",
                        "license": "commercial-owned",
                        "source_sha256": digest,
                        "start_sec": 0,
                        "duration_sec": 0.1,
                    }
                ]
            },
            duration_sec=1,
            out=tmp_path / "audio" / "scene-copied.wav",
            sample_rate=8000,
        )


def test_scene_stem_rejects_metadata_stripped_stable_audio(tmp_path: Path):
    asset = tmp_path / "assets" / "rain.wav"
    asset.parent.mkdir()
    with wave.open(str(asset), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 800)
    with pytest.raises(SceneSoundError, match="candidate"):
        render_scene_sound_stem(
            tmp_path,
            {
                "events": [
                    {
                        "id": "stable",
                        "type": "ambience",
                        "source": "local:assets/rain.wav",
                        "source_sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
                        "license": "Stability AI Community License",
                        "start_sec": 0,
                        "duration_sec": 0.1,
                    }
                ]
            },
            duration_sec=1,
            out=tmp_path / "audio" / "scene.wav",
            sample_rate=8000,
        )


def test_scene_stem_rejects_pending_ambient_candidate(tmp_path: Path):
    asset = tmp_path / "audio" / "candidates" / "ambient" / "pending" / "rain.wav"
    asset.parent.mkdir(parents=True)
    with wave.open(str(asset), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 800)

    with pytest.raises(SceneSoundError, match="pending candidate"):
        render_scene_sound_stem(
            tmp_path,
            {
                "events": [
                    {
                        "id": "ambient-candidate",
                        "type": "ambience",
                        "source": "local:audio/candidates/ambient/pending/rain.wav",
                        "license": "Stability AI Community License",
                        "source_sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
                        "approval_status": "pending_human_review",
                        "production_eligible": False,
                        "start_sec": 0,
                        "duration_sec": 0.1,
                    }
                ]
            },
            duration_sec=1,
            out=tmp_path / "audio" / "ambient.wav",
            sample_rate=8000,
        )


def test_rendered_scene_stem_survives_a_real_mp4_audio_mix(tmp_path: Path):
    asset = tmp_path / "assets" / "tone.wav"
    asset.parent.mkdir()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=0.2",
            str(asset),
        ],
        check=True,
    )
    result = render_scene_sound_stem(
        tmp_path,
        {
            "events": [
                {
                    "id": "tone",
                    "type": "action_sfx",
                    "source": "local:assets/tone.wav",
                    "source_sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
                    "start_sec": 0.1,
                    "duration_sec": 0.2,
                }
            ]
        },
        duration_sec=0.5,
        out=tmp_path / "audio" / "scene.wav",
        sample_rate=48000,
    )
    output = tmp_path / "final.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=size=64x64:rate=24:duration=0.5",
            "-i",
            result["path"],
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(output),
        ],
        check=True,
    )
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type,sample_rate,channels",
            "-of",
            "default=noprint_wrappers=1",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "codec_type=audio" in probe.stdout
    assert "sample_rate=48000" in probe.stdout
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(output), "-f", "f32le", "-ac", "2", "pipe:1"],
        capture_output=True,
        check=True,
    )
    assert np.max(np.abs(np.frombuffer(decoded.stdout, dtype=np.float32))) > 0.01


def test_walk_open_door_and_ambience_complete_the_local_scene_sound_loop(tmp_path: Path):
    asset = tmp_path / "assets" / "room-tone.wav"
    asset.parent.mkdir()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            str(asset),
        ],
        check=True,
    )
    checksum = hashlib.sha256(asset.read_bytes()).hexdigest()
    spec = {
        "shots": [
            {
                "id": "s1",
                "duration_sec": 1,
                "action": "她走到门边，推门进入。",
                "floor_material": "wood",
                "door_material": "wood",
                "audio_cues": [
                    {
                        "kind": "ambience",
                        "source": "local:assets/room-tone.wav",
                        "source_sha256": checksum,
                        "license": "test-local",
                        "start_offset_sec": 0,
                        "duration_sec": 1,
                    },
                    {
                        "kind": "foley",
                        "asset_hint": "footsteps",
                        "material": "wood",
                        "source": "local:assets/room-tone.wav",
                        "source_sha256": checksum,
                        "license": "test-local",
                        "start_offset_sec": 0.1,
                        "duration_sec": 0.1,
                    },
                    {
                        "kind": "foley",
                        "asset_hint": "door_open",
                        "material": "wood",
                        "source": "local:assets/room-tone.wav",
                        "source_sha256": checksum,
                        "license": "test-local",
                        "start_offset_sec": 0.5,
                        "duration_sec": 0.1,
                    },
                ],
            }
        ]
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    assert reconcile(tmp_path, write=False)["status"] == "ok"
    result = render_scene_sound_stem(
        tmp_path,
        compile_timeline(spec),
        duration_sec=1,
        out=tmp_path / "audio" / "scene.wav",
        sample_rate=48000,
    )
    assert result["event_count"] == 3
    assert Path(result["path"]).is_file()
