from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import audio_tts_render
from audio_timeline import caption_bindings, compile_timeline


def test_event_tts_renderer_writes_wav_and_measured_duration(tmp_path: Path, monkeypatch):
    audio = tmp_path / "audio"
    audio.mkdir()
    timeline = compile_timeline(
        {
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
                            "spoken_text": "测试",
                            "start_offset_sec": 0,
                            "duration_sec": 1,
                        }
                    ],
                }
            ],
        }
    )
    event_id = timeline["events"][0]["id"]
    (audio / "audio-timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
    (audio / "caption-bindings.json").write_text(
        json.dumps(caption_bindings(timeline)), encoding="utf-8"
    )
    (audio / "tts-manifest.json").write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "audio_event_id": event_id,
                        "shot_id": "s1",
                        "text": "测试",
                        "provider": "edge",
                        "voice_id": "zh-CN-XiaoxiaoNeural",
                        "rate": "+0%",
                        "pitch": "+0Hz",
                        "asset_path": f"audio/tts-events/{event_id}.wav",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_synthesize(text, out_mp3, **kwargs):
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2", str(out_mp3)],
            check=True,
            capture_output=True,
        )
        return {"backend": "edge", "voice": kwargs["voice"]}

    monkeypatch.setattr(audio_tts_render, "synthesize", fake_synthesize)

    report = audio_tts_render.render_tts_events(tmp_path)

    assert report["ok"] is True
    manifest = json.loads((audio / "tts-manifest.json").read_text())
    assert manifest["jobs"][0]["status"] == "rendered"
    assert manifest["jobs"][0]["render_receipt"]["provider"] == "edge"
    assert (tmp_path / manifest["jobs"][0]["asset_path"]).is_file()


def test_event_tts_renderer_refuses_manifest_for_a_changed_timeline(tmp_path: Path):
    audio = tmp_path / "audio"
    audio.mkdir()
    timeline = compile_timeline(
        {"audio_style": "audiobook", "shots": [{"id": "s1", "duration_sec": 2, "nar": "测试"}]}
    )
    (audio / "audio-timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
    (audio / "tts-manifest.json").write_text(
        json.dumps({"timeline_sha256": "0" * 64, "jobs": []}), encoding="utf-8"
    )

    with pytest.raises(audio_tts_render.AudioTTSRenderError, match="timeline hash"):
        audio_tts_render.render_tts_events(tmp_path)
