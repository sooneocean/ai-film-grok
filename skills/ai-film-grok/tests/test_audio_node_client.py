from __future__ import annotations

import hashlib
import io
import json
import wave
from pathlib import Path
from unittest.mock import patch

import pytest
from audio_node_client import AudioNodeError, _url, health, render


def _delivery_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(b"\0\0\0\0" * 4410)
    return buffer.getvalue()


def test_rejects_non_http_node_url() -> None:
    with pytest.raises(AudioNodeError):
        _url("ssh://host", "/health")


def test_health_requires_private_token() -> None:
    with pytest.raises(AudioNodeError):
        health("http://192.168.88.52:8788", "short")


def test_render_rejects_unknown_kind(tmp_path: Path) -> None:
    with pytest.raises(AudioNodeError):
        render("http://192.168.88.52:8788", "x" * 32, "video", {}, tmp_path / "x.wav")


def test_render_rejects_non_wav_result(tmp_path: Path) -> None:
    replies = iter(
        [
            json.dumps({"job_id": "a"}).encode(),
            json.dumps({"status": "completed"}).encode(),
            b"not-wav",
        ]
    )
    with patch("audio_node_client._request", side_effect=lambda *args, **kwargs: next(replies)):
        with pytest.raises(AudioNodeError, match="invalid wav"):
            render(
                "http://192.168.88.52:8788",
                "x" * 32,
                "tts",
                {"text": "x"},
                tmp_path / "x.wav",
            )


def test_render_requires_receipt_hash_and_delivery_format(tmp_path: Path) -> None:
    wav = _delivery_wav()
    replies = iter(
        [
            json.dumps({"job_id": "a"}).encode(),
            json.dumps({"status": "completed", "sha256": hashlib.sha256(wav).hexdigest()}).encode(),
            wav,
        ]
    )
    with patch("audio_node_client._request", side_effect=lambda *args, **kwargs: next(replies)):
        receipt = render(
            "http://192.168.88.52:8788",
            "x" * 32,
            "tts",
            {"text": "x"},
            tmp_path / "x.wav",
        )

    assert receipt["sha256"] == hashlib.sha256(wav).hexdigest()


def test_render_discards_hash_mismatch(tmp_path: Path) -> None:
    wav = _delivery_wav()
    output = tmp_path / "x.wav"
    replies = iter(
        [
            json.dumps({"job_id": "a"}).encode(),
            json.dumps({"status": "completed", "sha256": "0" * 64}).encode(),
            wav,
        ]
    )
    with patch("audio_node_client._request", side_effect=lambda *args, **kwargs: next(replies)):
        with pytest.raises(AudioNodeError, match="hash"):
            render("http://192.168.88.52:8788", "x" * 32, "tts", {"text": "x"}, output)

    assert not output.exists()


def test_render_preserves_existing_asset_when_candidate_is_rejected(tmp_path: Path) -> None:
    wav = _delivery_wav()
    output = tmp_path / "x.wav"
    output.write_bytes(b"existing approved asset")
    replies = iter(
        [
            json.dumps({"job_id": "a"}).encode(),
            json.dumps({"status": "completed", "sha256": "0" * 64}).encode(),
            wav,
        ]
    )
    with patch("audio_node_client._request", side_effect=lambda *args, **kwargs: next(replies)):
        with pytest.raises(AudioNodeError, match="hash"):
            render("http://192.168.88.52:8788", "x" * 32, "tts", {"text": "x"}, output)

    assert output.read_bytes() == b"existing approved asset"


def test_render_rejects_unknown_terminal_state(tmp_path: Path) -> None:
    replies = iter(
        [json.dumps({"job_id": "a"}).encode(), json.dumps({"status": "cancelled"}).encode()]
    )
    with patch("audio_node_client._request", side_effect=lambda *args, **kwargs: next(replies)):
        with pytest.raises(AudioNodeError, match="unknown terminal"):
            render("http://192.168.88.52:8788", "x" * 32, "tts", {"text": "x"}, tmp_path / "x.wav")


def test_render_wraps_invalid_submission_json(tmp_path: Path) -> None:
    with patch("audio_node_client._request", return_value=b"not-json"):
        with pytest.raises(AudioNodeError, match="submission JSON"):
            render("http://192.168.88.52:8788", "x" * 32, "tts", {"text": "x"}, tmp_path / "x.wav")
