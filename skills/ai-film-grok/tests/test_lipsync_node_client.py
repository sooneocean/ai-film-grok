"""Lipsync node client tombstone (v2.40)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import lipsync_node_client as client  # noqa: E402
from lipsync_backend import LipSyncError  # noqa: E402


def test_health_frozen() -> None:
    h = client.health()
    assert h.get("frozen") is True
    assert h.get("ok") is False


def test_render_raises_if_present() -> None:
    render = getattr(client, "render", None)
    if render is None:
        return
    with pytest.raises((LipSyncError, client.LipsyncNodeError)):
        render("http://127.0.0.1:18790", "x" * 32, video="a.mp4", audio="b.wav")
