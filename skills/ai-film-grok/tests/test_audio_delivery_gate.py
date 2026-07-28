from __future__ import annotations

import sys
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from audio_delivery_gate import build_delivery_report
from audio_timeline import caption_bindings, compile_timeline


def _timeline():
    return compile_timeline(
        {"audio_style": "audiobook", "shots": [{"id": "s1", "duration_sec": 2, "nar": "测试旁白"}]}
    )


def test_delivery_gate_requires_ready_tts_and_exact_subtitle_bindings():
    timeline = _timeline()
    bindings = caption_bindings(timeline)
    manifest = {
        "jobs": [
            {
                "audio_event_id": timeline["events"][0]["id"],
                "request_sha256": "x",
                "status": "ready",
            }
        ]
    }

    report = build_delivery_report(
        timeline=timeline, tts_manifest=manifest, subtitle_bindings=bindings
    )

    assert report["ok"] is True


def test_delivery_gate_rejects_missing_tts_evidence_or_subtitle_drift():
    timeline = _timeline()
    report = build_delivery_report(
        timeline=timeline,
        tts_manifest={"jobs": []},
        subtitle_bindings=[],
    )

    assert report["ok"] is False
    assert any("subtitle bindings" in error for error in report["errors"])


def test_delivery_gate_marks_existing_delivery_stale_when_timeline_changes():
    timeline = _timeline()
    manifest = {
        "jobs": [
            {
                "audio_event_id": timeline["events"][0]["id"],
                "request_sha256": "x",
                "status": "ready",
            }
        ]
    }
    previous = build_delivery_report(
        timeline=timeline,
        tts_manifest=manifest,
        subtitle_bindings=caption_bindings(timeline),
    )
    previous["final_mp4"] = {"path": "film_final.mp4", "sha256": "a" * 64, "ffprobe": {}}
    changed = _timeline()
    changed["events"][0]["text"] = "已修改旁白"
    changed_manifest = {
        "jobs": [
            {
                "audio_event_id": changed["events"][0]["id"],
                "request_sha256": "x",
                "status": "ready",
            }
        ]
    }
    report = build_delivery_report(
        timeline=changed,
        tts_manifest=changed_manifest,
        subtitle_bindings=caption_bindings(changed),
        previous_report=previous,
    )
    assert report["ok"] is False
    assert report["stale"] is True
    assert report["stale_reason"] == "audio_timeline_changed"


def test_delivery_gate_requires_checksum_bound_rendered_tts_asset(tmp_path: Path):
    timeline = _timeline()
    asset = tmp_path / "audio" / "tts" / "line.wav"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"rendered tts")
    manifest = {
        "jobs": [
            {
                "audio_event_id": timeline["events"][0]["id"],
                "request_sha256": "x",
                "status": "rendered",
                "asset_path": "audio/tts/line.wav",
                "asset_sha256": sha256(asset.read_bytes()).hexdigest(),
            }
        ]
    }
    report = build_delivery_report(
        timeline=timeline,
        tts_manifest=manifest,
        subtitle_bindings=caption_bindings(timeline),
        root=tmp_path,
    )
    assert report["ok"] is True
    asset.write_bytes(b"tampered")
    report = build_delivery_report(
        timeline=timeline,
        tts_manifest=manifest,
        subtitle_bindings=caption_bindings(timeline),
        root=tmp_path,
    )
    assert report["ok"] is False
    assert any("checksum changed" in error for error in report["errors"])
