from __future__ import annotations

import sys
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
