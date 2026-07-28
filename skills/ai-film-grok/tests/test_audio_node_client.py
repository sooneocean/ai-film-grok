from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from audio_node_client import AudioNodeError, _url, health, render


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
