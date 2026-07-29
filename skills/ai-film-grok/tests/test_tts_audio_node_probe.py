from __future__ import annotations

from unittest.mock import patch

import tts_backend


def test_audio_node_probe_rejects_legacy_health_without_variant_handshake(monkeypatch) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_NODE_URL", "http://192.168.88.52:8788")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    with patch(
        "audio_node_client.health", return_value={"ok": True, "models": {"tts": True}}
    ):
        report = tts_backend.probe_audio_node()
    assert report["ok"] is False
    assert "handshake" in report["error"]


def test_audio_node_probe_accepts_voice_design_handshake(monkeypatch) -> None:
    monkeypatch.setenv("AIFILM_AUDIO_NODE_URL", "http://192.168.88.52:8788")
    monkeypatch.setenv("AIFILM_AUDIO_NODE_TOKEN", "x" * 32)
    with patch(
        "audio_node_client.health",
        return_value={
            "ok": True,
            "models": {"tts": True},
            "tts_variants": {"voice_design": True, "custom_1_7b": False},
        },
    ):
        report = tts_backend.probe_audio_node()
    assert report["ok"] is True
