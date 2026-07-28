"""Fail-closed client for the private 5090 audio node."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from security_policy import atomic_write_bytes


class AudioNodeError(RuntimeError):
    pass


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
            return response.read()
    except urllib.error.URLError as exc:
        raise AudioNodeError("audio node unreachable") from exc


def health(base_url: str, token: str) -> dict[str, Any]:
    return json.loads(_request(base_url, token, "/health", timeout=15))


def render(
    base_url: str,
    token: str,
    kind: str,
    payload: dict[str, Any],
    out: Path,
    timeout: int = 900,
) -> dict[str, Any]:
    if kind not in {"tts", "music", "sfx"} or not base_url.startswith(("http://", "https://")):
        raise AudioNodeError("invalid private audio node request")
    if len(token) < 24:
        raise AudioNodeError("invalid private audio node request")

    job_id = json.loads(_request(base_url, token, f"/v1/{kind}", body=payload)).get("job_id")
    if not job_id:
        raise AudioNodeError("audio node did not return job id")
    for _ in range(timeout * 2):
        status = json.loads(_request(base_url, token, f"/v1/jobs/{job_id}"))
        if status.get("status") == "failed":
            raise AudioNodeError("audio node job failed")
        if status.get("status") == "completed":
            wav = _request(base_url, token, f"/v1/jobs/{job_id}/audio")
            if len(wav) < 512 or wav[:4] != b"RIFF":
                raise AudioNodeError("audio node returned invalid wav")
            atomic_write_bytes(out, wav)
            return {"job_id": job_id, "path": str(out), "sha256": status.get("sha256")}
        time.sleep(0.5)
    raise AudioNodeError("audio node job timed out")
