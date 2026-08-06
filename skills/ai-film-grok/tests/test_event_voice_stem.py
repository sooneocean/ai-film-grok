from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from audio_timeline import compile_timeline
from event_voice_stem import render_event_voice_stem


def test_event_voice_stem_renders_positioned_pan_filtered_assets(tmp_path: Path):
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
                            "spoken_text": "旁白",
                            "start_offset_sec": 0,
                            "duration_sec": 0.5,
                            "pan": -1,
                            "fade_in_sec": 0.05,
                        },
                        {
                            "kind": "voice",
                            "line_type": "inner_monologue",
                            "speaker": "hero",
                            "spoken_text": "心声",
                            "start_offset_sec": 1,
                            "duration_sec": 0.5,
                        },
                    ],
                }
            ],
        }
    )
    jobs = []
    for index, event in enumerate(timeline["events"]):
        path = tmp_path / "audio" / "tts-events" / f"{event['id']}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={440 + index * 100}:duration=0.4",
                "-ar",
                "48000",
                "-ac",
                "2",
                str(path),
            ],
            check=True,
            capture_output=True,
        )
        jobs.append(
            {
                "audio_event_id": event["id"],
                "status": "rendered",
                "asset_path": str(path.relative_to(tmp_path)),
                "asset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )

    out = tmp_path / "audio" / "event-voices.wav"
    report = render_event_voice_stem(tmp_path, timeline, {"jobs": jobs}, duration_sec=2, out=out)

    assert out.is_file()
    assert report["event_count"] == 2
