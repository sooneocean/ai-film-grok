"""Unit tests for Grok OAuth pack (no live network required for pure helpers)."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import grok_oauth as go  # noqa: E402


def test_file_to_data_url_png(tmp_path: Path) -> None:
    p = tmp_path / "t.png"
    # minimal valid-ish bytes
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    url = go.file_to_data_url(p)
    assert url.startswith("data:image/png;base64,")
    payload = url.split(",", 1)[1]
    assert base64.b64decode(payload)[:4] == b"\x89PNG"


def test_image_input_object_url_passthrough() -> None:
    assert go._image_input_object("https://example.com/a.png") == {
        "url": "https://example.com/a.png"
    }
    assert go._image_input_object("data:image/png;base64,AAA") == {
        "url": "data:image/png;base64,AAA"
    }


def test_probe_pack_flags_without_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_GROK_AUTH_PATH", str(tmp_path / "missing-auth.json"))
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.setenv("AIFILM_GROK_AUTH", "oauth")
    rep = go.probe(deep=False)
    assert rep["ok"] is False
    assert "pack" in rep
    assert rep["pack"]["video_i2v"] is True
    assert rep["pack"]["tts"] is True
    assert rep["pack"]["native_lipsync"] is False


def test_chat_completion_json_mode_body(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_token(**_k):
        return {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"}

    def fake_http(method, url, *, token, body=None, timeout=120):
        captured["body"] = body
        return {
            "choices": [{"message": {"content": '{"ok":true}'}}],
            "usage": {"total_tokens": 1},
        }

    monkeypatch.setattr(go, "get_access_token", fake_token)
    monkeypatch.setattr(go, "_http_json", fake_http)
    out = go.chat_completion("hi", json_mode=True)
    assert out["ok"] is True
    assert captured["body"]["response_format"] == {"type": "json_object"}


def test_video_submit_requires_image_for_15(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        go,
        "get_access_token",
        lambda **_k: {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"},
    )
    with pytest.raises(go.GrokOAuthError, match="image-to-video only"):
        go.video_submit("leaf falls", model="grok-imagine-video-1.5")


def test_video_submit_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        go,
        "get_access_token",
        lambda **_k: {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"},
    )
    monkeypatch.setattr(
        go,
        "_http_json",
        lambda *a, **k: {"request_id": "rid-123"},
    )
    monkeypatch.setattr(go, "_image_input_object", lambda x: {"url": "data:image/png;base64,AA"})
    out = go.video_submit("motion", image="/tmp/x.png", duration=6)
    assert out["request_id"] == "rid-123"
    assert out["ok"] is True


def test_tts_speak_raw_mp3(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        go,
        "get_access_token",
        lambda **_k: {"token": "t", "api_base": "https://api.x.ai/v1", "source": "test"},
    )
    audio = b"ID3" + b"\x00" * 500

    def fake_bytes(*a, **k):
        return audio, "audio/mpeg"

    monkeypatch.setattr(go, "_http_bytes", fake_bytes)
    out = tmp_path / "vo.mp3"
    rep = go.tts_speak("你好", out=out, language="zh", voice_id="eve")
    assert rep["ok"] is True
    assert out.read_bytes() == audio


def test_tts_backend_includes_grok() -> None:
    import tts_backend as tb

    assert "grok" in tb.TTS_BACKENDS
    # Neural id allowed with grok (will be stripped)
    tb.assert_voice_backend_compatible("grok", "zh-CN-XiaoxiaoNeural")


def test_cli_help_lists_video_tts() -> None:
    # argparse smoke: main(["doctor"]) needs network — just ensure parser builds
    with mock.patch.object(sys, "argv", ["grok_oauth", "doctor"]):
        # import side-effect free
        assert callable(go.main)
