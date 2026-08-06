"""Final heartbeat receipt (v2.40+)."""

from __future__ import annotations

import json
from pathlib import Path

from final.heartbeat import (
    HEARTBEAT_NAME,
    TIMEOUT_RECEIPT,
    apply_final_ffmpeg_timeout_env,
    default_ffmpeg_timeout_sec,
    write_final_heartbeat,
    write_final_timeout_receipt,
)


def test_write_heartbeat(tmp_path: Path):
    p = write_final_heartbeat(tmp_path, stage="stretch", detail="shot01")
    assert p.name == HEARTBEAT_NAME
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["stage"] == "stretch"
    assert data["pid"]
    assert data["unix"] > 0


def test_default_timeout():
    assert default_ffmpeg_timeout_sec() >= 60


def test_timeout_receipt(tmp_path: Path):
    p = write_final_timeout_receipt(
        tmp_path, stage="audio_mix", timeout_sec=900, error="ffmpeg hang"
    )
    assert p.name == TIMEOUT_RECEIPT
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["ok"] is False
    assert data["stage"] == "audio_mix"
    assert "next_cmd" in data
    assert (tmp_path / "receipts" / HEARTBEAT_NAME).is_file()


def test_apply_env(monkeypatch):
    monkeypatch.delenv("AIFILM_FFMPEG_TIMEOUT", raising=False)
    monkeypatch.delenv("AIFILM_FINAL_FFMPEG_TIMEOUT_SEC", raising=False)
    sec = apply_final_ffmpeg_timeout_env()
    assert sec >= 60
