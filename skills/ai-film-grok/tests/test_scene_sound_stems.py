from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from audio_timeline import compile_timeline
from scene_sound import reconcile
from scene_sound_stems import _apply_event_controls, render_scene_sound_stem


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


def test_scene_stem_requires_receipt_bound_performance_asset(tmp_path: Path):
    asset = tmp_path / "audio" / "candidates" / "performance" / "approved" / "take.wav"
    asset.parent.mkdir(parents=True)
    with wave.open(str(asset), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\0\0" * 800)
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    receipt = asset.with_suffix(".receipt.json")
    receipt.write_text(
        json.dumps(
            {
                "schema": "aifilm-performance-candidate-v1",
                "status": "approved",
                "approved_path": "audio/candidates/performance/approved/take.wav",
                "sha256": digest,
                "adult_confirmed": True,
                "source_authorization": "original",
                "take_seed": 42,
                "model_version": "higgs-audio-v2",
            }
        )
    )
    result = render_scene_sound_stem(
        tmp_path,
        {
            "events": [
                {
                    "id": "performance",
                    "type": "performance",
                    "source": "local:audio/candidates/performance/approved/take.wav",
                    "approval_receipt": "local:audio/candidates/performance/approved/take.receipt.json",
                    "source_sha256": digest,
                    "take_seed": 42,
                    "model_version": "higgs-audio-v2",
                    "start_sec": 0,
                    "duration_sec": 0.1,
                }
            ]
        },
        duration_sec=1,
        out=tmp_path / "audio" / "scene.wav",
        sample_rate=8000,
    )
    assert result["event_count"] == 1


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
