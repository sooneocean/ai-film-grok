"""Post lipsync removed (v2.40) — only off / fail-closed surfaces remain."""

from __future__ import annotations

import pytest

from lipsync_backend import (
    LIPSYNC_FROZEN_MSG,
    LipSyncError,
    enforce_dialogue_lipsync,
    lipsync_one,
    probe,
    should_lipsync_shot,
)


def test_probe_frozen_off():
    p = probe()
    assert p.get("frozen") is True
    assert p.get("env_backend") == "off"
    assert p.get("ready") == []


def test_should_never_lipsync():
    assert should_lipsync_shot({"dialogue": "你好"}) is False


def test_enforce_off_only():
    assert enforce_dialogue_lipsync(vo_mode="hybrid", shots=[], requested="off") == "off"
    with pytest.raises(LipSyncError) as ei:
        enforce_dialogue_lipsync(vo_mode="hybrid", shots=[], requested="auto")
    assert "removed" in str(ei.value).lower() or "frozen" in LIPSYNC_FROZEN_MSG.lower()


def test_lipsync_one_raises():
    with pytest.raises(LipSyncError):
        lipsync_one(video="/tmp/a.mp4", audio="/tmp/a.wav", out="/tmp/o.mp4")
