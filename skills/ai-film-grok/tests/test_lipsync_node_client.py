from __future__ import annotations

import hashlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lipsync_node_client import (  # noqa: E402
    LipsyncNodeError,
    _multipart,
    _request,
    _url,
    health,
    render,
)


def test_multipart_upload_streams_with_bounded_content_length(tmp_path: Path) -> None:
    uploaded: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            uploaded["content_length"] = int(self.headers["Content-Length"])
            uploaded["transfer_encoding"] = self.headers.get("Transfer-Encoding")
            uploaded["body"] = self.rfile.read(int(self.headers["Content-Length"]))
            payload = b'{"job_id":"streamed"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args) -> None:
            return

    video = tmp_path / "input.mp4"
    video.write_bytes(b"stream-me")
    body, content_type = _multipart(fields={"backend": "latentsync"}, files={"video": video})
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = _request(
            f"http://127.0.0.1:{server.server_port}",
            "x" * 32,
            "/v1/lipsync/jobs",
            method="POST",
            body=body,
            content_type=content_type,
        )
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

    assert json.loads(response)["job_id"] == "streamed"
    assert uploaded["content_length"] == body.content_length
    assert uploaded["transfer_encoding"] is None
    assert b"stream-me" in uploaded["body"]


def test_url_requires_private_literal_host() -> None:
    assert _url("http://127.0.0.1:18790", "/health").endswith("/health")
    assert _url("https://192.168.88.52:8790", "/health").endswith("/health")
    with pytest.raises(LipsyncNodeError, match="HTTPS"):
        _url("http://192.168.88.52:8790", "/health")
    with pytest.raises(LipsyncNodeError):
        _url("https://example.com", "/health")
    with pytest.raises(LipsyncNodeError):
        _url("https://169.254.169.254", "/health")
    with pytest.raises(LipsyncNodeError):
        _url("https://198.18.0.1", "/health")
    with pytest.raises(LipsyncNodeError):
        _url("ssh://192.168.88.52", "/health")
    for unsafe in (
        "https://169.254.169.254:8790",
        "https://0.0.0.0:8790",
        "https://192.0.2.1:8790",
        "https://[fe80::1]:8790",
    ):
        with pytest.raises(LipsyncNodeError):
            _url(unsafe, "/health")


def test_health_requires_private_token() -> None:
    with pytest.raises(LipsyncNodeError):
        health("http://127.0.0.1:18790", "short")


def test_render_downloads_hash_bound_mp4_atomically(tmp_path: Path) -> None:
    video = tmp_path / "input.mp4"
    audio = tmp_path / "input.wav"
    output = tmp_path / "output.mp4"
    video.write_bytes(b"video input")
    audio.write_bytes(b"audio input")
    artifact = b"\x00\x00\x00\x18ftypmp42verified-video"
    receipt = {
        "job_id": "job-1",
        "status": "completed",
        "requested_backend": "latentsync",
        "chosen_backend": "latentsync",
        "fallback_backend": "musetalk",
        "input_video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
        "input_audio_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
        "parameters": {"inference_steps": 20, "guidance_scale": 1.5, "deepcache": True},
        "output_sha256": hashlib.sha256(artifact).hexdigest(),
        "ffprobe": {"duration": 4.0, "fps": 25.0, "video_codec": "h264"},
    }
    replies = iter(
        [
            json.dumps({"job_id": "job-1"}).encode(),
            json.dumps(receipt).encode(),
        ]
    )

    with (
        patch("lipsync_node_client._request", side_effect=lambda *a, **k: next(replies)),
        patch(
            "lipsync_node_client._download_artifact",
            side_effect=lambda _base, _token, _job, path: path.write_bytes(artifact),
        ),
        patch("lipsync_node_client._validate_mp4", return_value=receipt["ffprobe"]),
    ):
        result = render(
            "http://127.0.0.1:18790",
            "x" * 32,
            video=video,
            audio=audio,
            out=output,
            backend="latentsync",
            fallback_backend="musetalk",
        )

    assert output.read_bytes() == artifact
    assert result["chosen_backend"] == "latentsync"
    assert result["output_sha256"] == hashlib.sha256(artifact).hexdigest()
    assert not list(tmp_path.glob("*.partial"))


def test_render_preserves_existing_output_on_hash_mismatch(tmp_path: Path) -> None:
    video = tmp_path / "input.mp4"
    audio = tmp_path / "input.wav"
    output = tmp_path / "output.mp4"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    output.write_bytes(b"approved")
    replies = iter(
        [
            json.dumps({"job_id": "job-2"}).encode(),
            json.dumps(
                {
                    "job_id": "job-2",
                    "status": "completed",
                    "requested_backend": "latentsync",
                    "chosen_backend": "latentsync",
                    "fallback_backend": None,
                    "input_video_sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
                    "input_audio_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
                    "parameters": {
                        "inference_steps": 20,
                        "guidance_scale": 1.5,
                        "deepcache": True,
                    },
                    "output_sha256": "0" * 64,
                    "ffprobe": {"duration": 1.0, "fps": 25.0},
                }
            ).encode(),
        ]
    )
    candidate = b"\x00\x00\x00\x18ftypmp42candidate"

    with (
        patch("lipsync_node_client._request", side_effect=lambda *a, **k: next(replies)),
        patch(
            "lipsync_node_client._download_artifact",
            side_effect=lambda _base, _token, _job, path: path.write_bytes(candidate),
        ),
        patch("lipsync_node_client._validate_mp4", return_value={"duration": 1.0}),
    ):
        with pytest.raises(LipsyncNodeError, match="hash"):
            render(
                "http://127.0.0.1:18790",
                "x" * 32,
                video=video,
                audio=audio,
                out=output,
                backend="latentsync",
            )

    assert output.read_bytes() == b"approved"


def test_render_rejects_receipt_from_another_input(tmp_path: Path) -> None:
    video = tmp_path / "input.mp4"
    audio = tmp_path / "input.wav"
    output = tmp_path / "output.mp4"
    video.write_bytes(b"video")
    audio.write_bytes(b"audio")
    replies = iter(
        [
            json.dumps({"job_id": "job-3"}).encode(),
            json.dumps(
                {
                    "job_id": "job-3",
                    "status": "completed",
                    "requested_backend": "latentsync",
                    "chosen_backend": "latentsync",
                    "fallback_backend": None,
                    "input_video_sha256": "0" * 64,
                    "input_audio_sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
                    "parameters": {
                        "inference_steps": 20,
                        "guidance_scale": 1.5,
                        "deepcache": True,
                    },
                }
            ).encode(),
        ]
    )
    with patch("lipsync_node_client._request", side_effect=lambda *a, **k: next(replies)):
        with pytest.raises(LipsyncNodeError, match="receipt"):
            render(
                "http://127.0.0.1:18790",
                "x" * 32,
                video=video,
                audio=audio,
                out=output,
                backend="latentsync",
            )

    assert not output.exists()
