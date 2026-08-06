"""Post lipsync frozen (v2.40): only --lipsync off is production-legal."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lipsync_backend  # noqa: E402


def test_should_lipsync_shot_always_false() -> None:
    valid = {
        "lipsync": True,
        "speaker": "hero",
        "face_target": "hero",
        "dsl": {"camera": {"shot_size": "close-up", "angle": "front"}},
    }
    assert lipsync_backend.should_lipsync_shot(valid) is False
    assert lipsync_backend.should_lipsync_shot(None) is False


def test_dialogue_only_allows_lipsync_off() -> None:
    assert (
        lipsync_backend.enforce_dialogue_lipsync(
            vo_mode="dialogue_drama",
            requested="off",
            shots=[{"id": "talk01", "screen_mode": "on_camera"}],
        )
        == "off"
    )
    with pytest.raises(lipsync_backend.LipSyncError, match="removed|prefer_native|frozen"):
        lipsync_backend.enforce_dialogue_lipsync(
            vo_mode="dialogue_drama",
            requested="auto",
            shots=[{"id": "talk01", "screen_mode": "on_camera"}],
        )
    with pytest.raises(lipsync_backend.LipSyncError):
        lipsync_backend.enforce_dialogue_lipsync(
            vo_mode="dialogue_drama",
            requested="require",
            shots=[{"id": "talk01"}],
        )


def test_probe_reports_frozen() -> None:
    info = lipsync_backend.probe()
    assert info.get("frozen") is True
    assert info.get("ok") is True
    assert info.get("ready") == []


def test_lipsync_one_raises() -> None:
    with pytest.raises(lipsync_backend.LipSyncError):
        lipsync_backend.lipsync_one(video="a.mp4", audio="b.wav", out="c.mp4")
