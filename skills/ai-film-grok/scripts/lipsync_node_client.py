#!/usr/bin/env python3
"""Private-LAN RTX lip-sync node client with hash-bound MP4 promotion."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import mimetypes
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


class LipsyncNodeError(RuntimeError):
    pass


_JOB_ID = re.compile(r"^[A-Za-z0-9-]{1,80}$")
_BACKENDS = {"latentsync", "musetalk"}
_MAX_VIDEO_BYTES = 512 * 1024 * 1024
_MAX_AUDIO_BYTES = 64 * 1024 * 1024
_ALLOWED_NODE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _MultipartBody:
    def __init__(self, segments: list[bytes | Path]):
        self.segments = segments
        self.content_length = sum(
            len(segment) if isinstance(segment, bytes) else segment.stat().st_size
            for segment in segments
        )

    def __iter__(self):
        for segment in self.segments:
            if isinstance(segment, bytes):
                yield segment
                continue
            with segment.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    yield chunk


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _url(base_url: str, path: str) -> str:
    parsed = urlsplit(str(base_url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise LipsyncNodeError("lip-sync node URL must be HTTP(S)")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError as exc:
        raise LipsyncNodeError("lip-sync node host must be a private IP literal") from exc
    if not (
        address.is_loopback
        or any(
            address.version == network.version and address in network
            for network in _ALLOWED_NODE_NETWORKS
        )
    ):
        raise LipsyncNodeError("lip-sync node host must be private or loopback")
    if parsed.scheme == "http" and not address.is_loopback:
        raise LipsyncNodeError("private-LAN lip-sync nodes require HTTPS or a loopback tunnel")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise LipsyncNodeError("lip-sync node URL must not contain credentials or query data")
    clean_path = "/" + path.lstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, clean_path, "", ""))


def _token(token: str) -> str:
    value = str(token or "").strip()
    if len(value) < 32:
        raise LipsyncNodeError("lip-sync node token must contain at least 32 characters")
    return value


def _json(raw: bytes, *, context: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LipsyncNodeError(f"lip-sync node returned invalid {context} JSON") from exc
    if not isinstance(value, dict):
        raise LipsyncNodeError(f"lip-sync node returned invalid {context} JSON")
    return value


def _multipart(
    *,
    fields: dict[str, str],
    files: dict[str, Path],
) -> tuple[_MultipartBody, str]:
    boundary = f"aifilm-{uuid.uuid4().hex}"
    chunks: list[bytes | Path] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, path in files.items():
        filename = path.name.replace('"', "_").replace("\r", "_").replace("\n", "_")
        mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                ).encode(),
                f"Content-Type: {mime}\r\n\r\n".encode(),
                path,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return _MultipartBody(chunks), f"multipart/form-data; boundary={boundary}"


def _request(
    base_url: str,
    token: str,
    path: str,
    *,
    method: str = "GET",
    body: bytes | _MultipartBody | None = None,
    content_type: str | None = None,
    timeout: int = 30,
    expect_mp4: bool = False,
) -> bytes:
    headers = {
        "Authorization": f"Bearer {_token(token)}",
        "Accept": "video/mp4" if expect_mp4 else "application/json",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if isinstance(body, _MultipartBody):
        headers["Content-Length"] = str(body.content_length)
    request = urllib.request.Request(
        _url(base_url, path),
        data=body,
        method=method,
        headers=headers,
    )

    opener = urllib.request.build_opener(_RejectRedirects)
    try:
        with opener.open(request, timeout=timeout) as response:
            content_type_received = str(response.headers.get("Content-Type") or "").lower()
            if expect_mp4 and "video/mp4" not in content_type_received:
                raise LipsyncNodeError("lip-sync node returned invalid artifact MIME type")
            limit = _MAX_VIDEO_BYTES if expect_mp4 else 2 * 1024 * 1024
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > limit:
                raise LipsyncNodeError("lip-sync node response exceeds size limit")
            payload = response.read(limit + 1)
            if len(payload) > limit:
                raise LipsyncNodeError("lip-sync node response exceeds size limit")
            return payload
    except urllib.error.HTTPError as exc:
        raise LipsyncNodeError(f"lip-sync node HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise LipsyncNodeError("lip-sync node unreachable") from exc


def _download_artifact(
    base_url: str,
    token: str,
    job_id: str,
    destination: Path,
) -> None:
    request = urllib.request.Request(
        _url(base_url, f"/v1/lipsync/jobs/{job_id}/artifact"),
        method="GET",
        headers={
            "Authorization": f"Bearer {_token(token)}",
            "Accept": "video/mp4",
        },
    )
    opener = urllib.request.build_opener(_RejectRedirects)
    try:
        with opener.open(request, timeout=180) as response:
            content_type = str(response.headers.get("Content-Type") or "").lower()
            if "video/mp4" not in content_type:
                raise LipsyncNodeError("lip-sync node returned invalid artifact MIME type")
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > _MAX_VIDEO_BYTES:
                raise LipsyncNodeError("lip-sync node response exceeds size limit")
            total = 0
            prefix = b""
            with destination.open("xb") as handle:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > _MAX_VIDEO_BYTES:
                        raise LipsyncNodeError("lip-sync node response exceeds size limit")
                    if len(prefix) < 64:
                        prefix = (prefix + chunk)[:64]
                    handle.write(chunk)
            if total < 16 or b"ftyp" not in prefix:
                raise LipsyncNodeError("lip-sync node returned invalid MP4")
    except urllib.error.HTTPError as exc:
        raise LipsyncNodeError(f"lip-sync node HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise LipsyncNodeError("lip-sync node unreachable") from exc


def health(base_url: str, token: str) -> dict[str, Any]:
    return _json(_request(base_url, token, "/health", timeout=360), context="health")


def _validate_input(path: Path, *, limit: int, label: str) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise LipsyncNodeError(f"{label} must be a regular non-symlink file")
    resolved = expanded.resolve()
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        raise LipsyncNodeError(f"{label} is missing or empty")
    if resolved.stat().st_size > limit:
        raise LipsyncNodeError(f"{label} exceeds upload limit")
    return resolved


def _validate_mp4(path: Path) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height,avg_frame_rate,nb_frames:format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(proc.stdout)
        stream = (payload.get("streams") or [])[0]
        duration = float((payload.get("format") or {}).get("duration") or 0)
        rate = str(stream.get("avg_frame_rate") or "0/1")
        numerator, denominator = rate.split("/", 1)
        fps = float(numerator) / max(float(denominator), 1.0)
    except (
        IndexError,
        OSError,
        ValueError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ) as exc:
        raise LipsyncNodeError("lip-sync node MP4 failed ffprobe") from exc
    if duration <= 0 or fps <= 0 or int(stream.get("width") or 0) <= 0:
        raise LipsyncNodeError("lip-sync node MP4 has invalid video metadata")
    return {
        "duration": duration,
        "fps": fps,
        "video_codec": stream.get("codec_name"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "frames": stream.get("nb_frames"),
    }


def render(
    base_url: str,
    token: str,
    *,
    video: Path,
    audio: Path,
    out: Path,
    backend: str,
    fallback_backend: str = "",
    inference_steps: int = 20,
    guidance_scale: float = 1.5,
    deepcache: bool = True,
    timeout: int = 1800,
) -> dict[str, Any]:
    if backend not in _BACKENDS:
        raise LipsyncNodeError(f"unsupported node backend: {backend}")
    if fallback_backend and fallback_backend not in _BACKENDS - {backend}:
        raise LipsyncNodeError("invalid lip-sync fallback backend")
    if not 1 <= int(inference_steps) <= 100 or not 0.1 <= float(guidance_scale) <= 10:
        raise LipsyncNodeError("invalid lip-sync inference parameters")
    source_video = _validate_input(video, limit=_MAX_VIDEO_BYTES, label="video")
    source_audio = _validate_input(audio, limit=_MAX_AUDIO_BYTES, label="audio")
    input_video_sha256 = _sha256_file(source_video)
    input_audio_sha256 = _sha256_file(source_audio)
    output = out.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    payload, content_type = _multipart(
        fields={
            "backend": backend,
            "fallback_backend": fallback_backend,
            "inference_steps": str(int(inference_steps)),
            "guidance_scale": str(float(guidance_scale)),
            "deepcache": "true" if deepcache else "false",
        },
        files={"video": source_video, "audio": source_audio},
    )
    submission = _json(
        _request(
            base_url,
            token,
            "/v1/lipsync/jobs",
            method="POST",
            body=payload,
            content_type=content_type,
            timeout=180,
        ),
        context="submission",
    )
    job_id = str(submission.get("job_id") or "")
    if not _JOB_ID.fullmatch(job_id):
        raise LipsyncNodeError("lip-sync node returned invalid job id")

    deadline = time.monotonic() + timeout
    status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status = _json(
            _request(base_url, token, f"/v1/lipsync/jobs/{job_id}", timeout=30),
            context="job status",
        )
        state = status.get("status")
        if state == "failed":
            failure = status.get("failure") or {}
            raise LipsyncNodeError(
                f"lip-sync node job failed ({failure.get('failure_class') or 'unknown'})"
            )
        if state == "completed":
            break
        if state not in {"queued", "running"}:
            raise LipsyncNodeError("lip-sync node entered an unknown terminal state")
        time.sleep(0.5)
    else:
        raise LipsyncNodeError("lip-sync node job timed out")

    expected_parameters = {
        "inference_steps": int(inference_steps),
        "guidance_scale": float(guidance_scale),
        "deepcache": bool(deepcache),
    }
    if (
        status.get("job_id") != job_id
        or not secrets.compare_digest(
            str(status.get("input_video_sha256") or ""), input_video_sha256
        )
        or not secrets.compare_digest(
            str(status.get("input_audio_sha256") or ""), input_audio_sha256
        )
        or status.get("requested_backend") != backend
        or status.get("fallback_backend") != (fallback_backend or None)
        or status.get("parameters") != expected_parameters
        or status.get("chosen_backend") not in {backend, fallback_backend}
    ):
        raise LipsyncNodeError("lip-sync node receipt does not match request")

    partial = output.with_name(f".{output.name}.{job_id}.partial")
    try:
        _download_artifact(base_url, token, job_id, partial)
        local_probe = _validate_mp4(partial)
        actual_hash = _sha256_file(partial)
        if actual_hash != status.get("output_sha256"):
            raise LipsyncNodeError("lip-sync node MP4 hash does not match receipt")
        remote_probe = status.get("ffprobe") or {}
        if (
            remote_probe
            and abs(float(remote_probe.get("duration") or 0) - local_probe["duration"]) > 0.1
        ):
            raise LipsyncNodeError("lip-sync node MP4 metadata does not match receipt")
        partial.replace(output)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    return {
        **status,
        "job_id": job_id,
        "path": str(output),
        "output_sha256": actual_hash,
        "local_ffprobe": local_probe,
    }
