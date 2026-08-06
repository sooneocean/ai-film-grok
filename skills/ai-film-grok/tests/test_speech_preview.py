from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import speech_preview  # noqa: E402


def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIFILM_SPEECH_PREVIEW_URL", "http://127.0.0.1:8765")
    monkeypatch.setenv("AIFILM_SPEECH_PREVIEW_GUARD_ARGV", '["guard"]')
    monkeypatch.setenv(
        "AIFILM_SPEECH_PREVIEW_START_ARGV",
        '["speech-to-speech","--ws_host","127.0.0.1","--stt","whisper","--tts","qwen3","--llm_backend","responses-api"]',
    )


def test_probe_is_configuration_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _configured(monkeypatch)
    report = speech_preview.probe()
    assert report["ok"] is True
    assert report["inference_started"] is False
    assert report["candidate_only"] is True


def test_probe_rejects_non_loopback_and_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    _configured(monkeypatch)
    monkeypatch.setenv("AIFILM_SPEECH_PREVIEW_URL", "http://0.0.0.0:8765")
    monkeypatch.setenv(
        "AIFILM_SPEECH_PREVIEW_START_ARGV",
        '["speech-to-speech","--ws_host","127.0.0.1","--stt","whisper","--tts","qwen3","--llm_backend","responses-api","--enable_llm_proxy"]',
    )
    report = speech_preview.probe()
    assert report["ok"] is False
    assert any("loopback" in issue for issue in report["issues"])
    assert any("proxy" in issue for issue in report["issues"])


def test_start_refuses_busy_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    _configured(monkeypatch)
    monkeypatch.setattr(
        speech_preview.subprocess,
        "run",
        lambda *_args, **_kwargs: type(
            "Result", (), {"returncode": 0, "stdout": json.dumps({"queue_idle": False})}
        )(),
    )
    with pytest.raises(speech_preview.SpeechPreviewError, match="queue"):
        speech_preview.start(confirm=True)


def test_session_and_export_are_hash_bound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "film"
    root.mkdir()
    audio = root / "take.wav"
    audio.write_bytes(b"RIFF")
    payload = root / "session.json"
    payload.write_text(
        json.dumps(
            {
                "recognized_text": "你好",
                "reply_text": "你好，导演",
                "language": "zh",
                "first_audio_latency_ms": 120,
                "response_latency_ms": 420,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        speech_preview, "analyze_media", lambda *_args, **_kwargs: {"has_audio": True, "ok": True}
    )
    monkeypatch.setattr(speech_preview, "verify_full_decode", lambda *_args, **_kwargs: None)
    session = speech_preview.record_session(root, audio=audio, session_json=payload)
    candidate = speech_preview.export_candidate(root, session_receipt=session["path"])
    assert candidate["status"] == "awaiting_human_listening"
    assert candidate["restrictions"] == ["not_final_audio", "not_tts_backend", "no_auto_approval"]
