"""Final heartbeat receipt (v2.40)."""

from __future__ import annotations

import json
from pathlib import Path

from final.heartbeat import HEARTBEAT_NAME, default_ffmpeg_timeout_sec, write_final_heartbeat


def test_write_heartbeat(tmp_path: Path):
    p = write_final_heartbeat(tmp_path, stage="stretch", detail="shot01")
    assert p.name == HEARTBEAT_NAME
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["stage"] == "stretch"
    assert data["pid"]
    assert data["unix"] > 0


def test_default_timeout():
    assert default_ffmpeg_timeout_sec() >= 60
