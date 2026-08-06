from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from audio_event_editor import AudioEventEditError, edit_event
from audio_timeline import compile_timeline


def _timeline():
    return compile_timeline(
        {"audio_style": "audiobook", "shots": [{"id": "s1", "duration_sec": 2, "nar": "原文"}]}
    )


def test_event_editor_updates_mix_controls_without_mutating_source():
    timeline = _timeline()
    event_id = timeline["events"][0]["id"]
    edited, manifest, bindings = edit_event(
        timeline, event_id, {"gain": 0.7, "pan": -0.4, "fade_in_sec": 0.1}
    )

    assert timeline["events"][0]["gain"] == 1.0
    assert edited["events"][0]["gain"] == 0.7
    assert manifest is None
    assert bindings[0]["audio_event_id"] == event_id


def test_event_editor_marks_tts_stale_after_text_change_and_respects_lock():
    timeline = _timeline()
    event_id = timeline["events"][0]["id"]
    manifest = {"jobs": [{"audio_event_id": event_id, "status": "rendered"}]}
    _, updated_manifest, _ = edit_event(
        timeline, event_id, {"text": "新文本"}, tts_manifest=manifest
    )
    assert updated_manifest["jobs"][0]["status"] == "stale"

    timeline["events"][0]["locked"] = True
    with pytest.raises(AudioEventEditError, match="locked"):
        edit_event(timeline, event_id, {"gain": 0.5})
