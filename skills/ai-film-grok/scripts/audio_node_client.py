"""Fail-closed client for the private 5090 audio node."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from security_policy import atomic_write_bytes


class AudioNodeError(RuntimeError):
    pass


def _json_response(payload: bytes, *, context: str) -> dict[str, Any]:
    try:
        data = json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AudioNodeError(f"audio node returned invalid {context} JSON") from exc
    if not isinstance(data, dict):
        raise AudioNodeError(f"audio node returned invalid {context} JSON")
    return data


def _url(base_url: str, path: str) -> str:
    if not base_url.startswith(("http://", "https://")):
        raise AudioNodeError("audio node URL must use http(s)")
    return base_url.rstrip("/") + path


def _request(
    base_url: str,
    token: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
    expect_wav: bool = False,
) -> bytes:
    if len(token) < 24:
        raise AudioNodeError("AIFILM_AUDIO_NODE_TOKEN is too short")
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(
        _url(base_url, path),
        data=data,
        method="POST" if body is not None else "GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if expect_wav:
                content_type = response.headers.get_content_type()
                if content_type not in {"audio/wav", "audio/x-wav"}:
                    raise AudioNodeError("audio node returned invalid MIME type")
            return response.read()
    except urllib.error.URLError as exc:
        raise AudioNodeError("audio node unreachable") from exc


def health(base_url: str, token: str) -> dict[str, Any]:
    return _json_response(_request(base_url, token, "/health", timeout=15), context="health")


def _validate_wav(path: Path) -> None:
    """Require the node's delivery format before promoting an artifact."""
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name,sample_rate,channels:format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        data = json.loads(probe.stdout)
        stream = (data.get("streams") or [])[0]
        duration = float((data.get("format") or {}).get("duration") or 0)
    except (
        IndexError,
        OSError,
        ValueError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ) as exc:
        raise AudioNodeError("audio node WAV failed ffprobe") from exc
    if (
        stream.get("codec_name") != "pcm_s16le"
        or str(stream.get("sample_rate")) != "44100"
        or stream.get("channels") != 2
        or duration <= 0
    ):
        raise AudioNodeError("audio node WAV does not meet delivery format")


def render(
    base_url: str,
    token: str,
    kind: str,
    payload: dict[str, Any],
    out: Path,
    timeout: int = 900,
) -> dict[str, Any]:
    if kind not in {"tts", "music", "sfx", "performance"} or not base_url.startswith(
        ("http://", "https://")
    ):
        raise AudioNodeError("invalid private audio node request")
    if len(token) < 24:
        raise AudioNodeError("invalid private audio node request")

    job_id = _json_response(
        _request(base_url, token, f"/v1/{kind}", body=payload), context="submission"
    ).get("job_id")
    if not job_id:
        raise AudioNodeError("audio node did not return job id")
    for _ in range(timeout * 2):
        status = _json_response(
            _request(base_url, token, f"/v1/jobs/{job_id}"), context="job status"
        )
        if status.get("status") == "failed":
            raise AudioNodeError("audio node job failed")
        if status.get("status") == "completed":
            wav = _request(base_url, token, f"/v1/jobs/{job_id}/audio", expect_wav=True)
            if len(wav) < 512 or wav[:4] != b"RIFF":
                raise AudioNodeError("audio node returned invalid wav")
            temporary = out.with_name(f".{out.name}.{job_id}.partial")
            try:
                atomic_write_bytes(temporary, wav)
                _validate_wav(temporary)
                actual_hash = hashlib.sha256(temporary.read_bytes()).hexdigest()
                if actual_hash != status.get("sha256"):
                    raise AudioNodeError("audio node WAV hash does not match receipt")
                temporary.replace(out)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            return {"job_id": job_id, "path": str(out), "sha256": actual_hash}
        if status.get("status") not in {"queued", "running"}:
            raise AudioNodeError("audio node job entered an unknown terminal state")
        time.sleep(0.5)
    raise AudioNodeError("audio node job timed out")
