#!/usr/bin/env python3
"""Authenticated single-GPU lip-sync service for a private Windows RTX node."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import time
import uuid
from pathlib import Path, PureWindowsPath
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)
JOBS_ROOT = Path(os.environ.get("AIFILM_LIPSYNC_NODE_ROOT", r"C:\aifilm-lipsync-node\jobs"))
jobs: dict[str, dict[str, Any]] = {}
gpu_lock = asyncio.Lock()
_backend_probe_cache: dict[tuple[str, ...], tuple[float, dict[str, Any] | None]] = {}

_BACKENDS = {"latentsync", "musetalk"}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_JOB_ID = re.compile(r"^[0-9a-f]{32}$")
_MAX_VIDEO_BYTES = 512 * 1024 * 1024
_MAX_AUDIO_BYTES = 64 * 1024 * 1024
_MAX_REQUEST_BYTES = _MAX_VIDEO_BYTES + _MAX_AUDIO_BYTES + 1024 * 1024


class BackendExecutionError(RuntimeError):
    def __init__(self, failure_class: str, message: str):
        super().__init__(message)
        self.failure_class = failure_class
        self.safe_message = message[:300]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = path.with_suffix(f"{path.suffix}.tmp")
    candidate.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    candidate.replace(path)


def _auth(authorization: str | None) -> None:
    expected = str(os.environ.get("AIFILM_LIPSYNC_NODE_TOKEN") or "")
    supplied = authorization or ""
    if len(expected) < 32 or not secrets.compare_digest(supplied, f"Bearer {expected}"):
        raise HTTPException(status_code=401, detail="unauthorized")


@app.middleware("http")
async def authenticate_before_body_parsing(request: Request, call_next):
    expected = str(os.environ.get("AIFILM_LIPSYNC_NODE_TOKEN") or "")
    supplied = request.headers.get("authorization") or ""
    if len(expected) < 32 or not secrets.compare_digest(supplied, f"Bearer {expected}"):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    if request.method == "POST":
        if request.headers.get("transfer-encoding"):
            return JSONResponse({"detail": "chunked requests are not accepted"}, status_code=411)
        try:
            content_length = int(request.headers.get("content-length") or "")
        except ValueError:
            content_length = -1
        if content_length <= 0 or content_length > _MAX_REQUEST_BYTES:
            return JSONResponse({"detail": "request size is invalid"}, status_code=413)
    return await call_next(request)


def _parse_argv(raw: str) -> list[str] | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if (
        not isinstance(value, list)
        or not value
        or len(value) > 128
        or any(not isinstance(item, str) or not item or "\x00" in item for item in value)
    ):
        return None
    return value


def _measure_backend(probe_argv: list[str] | None, *, force: bool = False) -> dict[str, Any] | None:
    if not probe_argv:
        return None
    key = tuple(probe_argv)
    cached = _backend_probe_cache.get(key)
    if not force and cached and time.monotonic() - cached[0] < 60:
        return cached[1]
    try:
        proc = subprocess.run(
            probe_argv,
            capture_output=True,
            text=True,
            timeout=330,
            check=True,
        )
        measured = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        measured = None
    result = measured if isinstance(measured, dict) else None
    _backend_probe_cache[key] = (time.monotonic(), result)
    return result


def _backend_info(backend: str, *, force_probe: bool = False) -> dict[str, Any]:
    if backend not in _BACKENDS:
        return {"backend": backend, "ready": False}
    prefix = f"AIFILM_LIPSYNC_NODE_{backend.upper()}"
    argv = _parse_argv(str(os.environ.get(f"{prefix}_ARGV") or ""))
    probe_argv = _parse_argv(str(os.environ.get(f"{prefix}_PROBE_ARGV") or ""))
    checkpoint = str(os.environ.get(f"{prefix}_CHECKPOINT_SHA256") or "").lower()
    commit = str(os.environ.get(f"{prefix}_REPO_COMMIT") or "")
    measured = _measure_backend(probe_argv, force=force_probe)
    measurement_matches = bool(
        measured
        and secrets.compare_digest(str(measured.get("checkpoint_sha256") or ""), checkpoint)
        and secrets.compare_digest(str(measured.get("repo_commit") or ""), commit)
        and measured.get("repo_dirty") is False
        and measured.get("gpu")
        and measured.get("pytorch")
        and measured.get("cuda")
    )
    technical_ready = bool(
        argv
        and probe_argv
        and _SHA256.fullmatch(checkpoint)
        and re.fullmatch(r"[0-9a-f]{40}", commit)
        and measurement_matches
    )
    approved = str(os.environ.get(f"{prefix}_APPROVED") or "").strip() == "1"
    model_default = "ByteDance/LatentSync-1.6" if backend == "latentsync" else "MuseTalk-1.5"
    return {
        "backend": backend,
        "ready": technical_ready and approved,
        "technical_ready": technical_ready,
        "approved": approved,
        "model": str(os.environ.get(f"{prefix}_MODEL") or model_default),
        "checkpoint_sha256": checkpoint or None,
        "repo_commit": commit or None,
        "argv_configured": bool(argv),
        "probe_configured": bool(probe_argv),
        "measured": measured,
    }


def _gpu_health() -> dict[str, Any]:
    try:
        proc = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        name, total, free, driver = [
            part.strip() for part in proc.stdout.splitlines()[0].split(",")
        ]
        return {
            "available": True,
            "name": name,
            "total_vram_mib": int(total),
            "free_vram_mib": int(free),
            "driver": driver,
        }
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        return {"available": False}


def _runtime() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "ffmpeg": _tool_version("ffmpeg", "-version"),
        "ffprobe": _tool_version("ffprobe", "-version"),
        "service_sha256": _sha256(Path(__file__).resolve()),
    }


def _tool_version(binary: str, flag: str) -> str | None:
    try:
        proc = subprocess.run(
            [binary, flag],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        return (proc.stdout or proc.stderr).splitlines()[0][:240]
    except (OSError, subprocess.SubprocessError, IndexError):
        return None


def _public_job(state: dict[str, Any]) -> dict[str, Any]:
    private = {"video_path", "audio_path", "artifact_path"}
    return {key: value for key, value in state.items() if key not in private}


def _persist_job(job_id: str) -> None:
    state = jobs.get(job_id)
    if state:
        _atomic_json(JOBS_ROOT / job_id / "receipt.json", _public_job(state))


def _load_job(job_id: str) -> dict[str, Any] | None:
    if not _JOB_ID.fullmatch(job_id):
        return None
    state = jobs.get(job_id)
    if state is not None:
        return state
    job_dir = JOBS_ROOT / job_id
    receipt = job_dir / "receipt.json"
    if (
        job_dir.is_symlink()
        or receipt.is_symlink()
        or not receipt.is_file()
        or receipt.stat().st_size > 1024 * 1024
    ):
        return None
    try:
        loaded = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict) or loaded.get("job_id") != job_id:
        return None
    if loaded.get("status") in {"queued", "running"}:
        loaded.update(
            {
                "status": "failed",
                "failure": {
                    "failure_class": "technical",
                    "message": "node restarted before job completion",
                },
            }
        )
    if loaded.get("status") == "completed":
        loaded["artifact_path"] = str(job_dir / "artifact.mp4")
    jobs[job_id] = loaded
    _persist_job(job_id)
    return loaded


def _may_fallback(failure_class: str) -> bool:
    return failure_class == "technical"


def _windows_to_wsl(path: Path) -> str:
    value = str(path.resolve())
    windows = PureWindowsPath(value)
    if windows.drive and len(windows.drive) == 2:
        drive = windows.drive[0].lower()
        tail = "/".join(windows.parts[1:])
        return f"/mnt/{drive}/{tail}"
    return value.replace("\\", "/")


def _expand_backend_argv(
    backend: str,
    *,
    video: Path,
    audio: Path,
    out: Path,
    parameters: dict[str, Any],
) -> list[str]:
    prefix = f"AIFILM_LIPSYNC_NODE_{backend.upper()}"
    template = _parse_argv(str(os.environ.get(f"{prefix}_ARGV") or ""))
    if not template:
        raise BackendExecutionError("technical", f"{backend} adapter is not configured")
    replacements = {
        "{video}": str(video),
        "{audio}": str(audio),
        "{out}": str(out),
        "{video_wsl}": _windows_to_wsl(video),
        "{audio_wsl}": _windows_to_wsl(audio),
        "{out_wsl}": _windows_to_wsl(out),
        "{inference_steps}": str(parameters["inference_steps"]),
        "{guidance_scale}": str(parameters["guidance_scale"]),
        "{deepcache}": "1" if parameters["deepcache"] else "0",
    }
    expanded: list[str] = []
    for item in template:
        value = item
        for placeholder, replacement in replacements.items():
            value = value.replace(placeholder, replacement)
        if "{" in value or "}" in value:
            raise BackendExecutionError("technical", f"{backend} adapter has unknown placeholder")
        expanded.append(value)
    return expanded


def _gpu_used_mib() -> int | None:
    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return int(proc.stdout.splitlines()[0].strip())
    except (OSError, ValueError, subprocess.SubprocessError, IndexError):
        return None


def _terminate_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            timeout=20,
        )
    else:
        proc.kill()


def _run_backend(
    backend: str,
    video: Path,
    audio: Path,
    out: Path,
    parameters: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    if not _backend_info(backend)["technical_ready"]:
        raise BackendExecutionError("technical", f"{backend} is not ready")
    argv = _expand_backend_argv(
        backend,
        video=video,
        audio=audio,
        out=out,
        parameters=parameters,
    )
    started = time.monotonic()
    peak = _gpu_used_mib()
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env={
                "PATH": os.environ.get("PATH", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                "WINDIR": os.environ.get("WINDIR", ""),
                "TEMP": os.environ.get("TEMP", ""),
                "TMP": os.environ.get("TMP", ""),
            },
        )
    except OSError as exc:
        raise BackendExecutionError("technical", f"{backend} adapter could not start") from exc
    deadline = started + int(os.environ.get("AIFILM_LIPSYNC_NODE_TIMEOUT", "1800"))
    while proc.poll() is None:
        if time.monotonic() >= deadline:
            _terminate_tree(proc)
            raise BackendExecutionError("technical", f"{backend} adapter timed out")
        used = _gpu_used_mib()
        if used is not None:
            peak = max(peak or used, used)
        time.sleep(0.5)
    proc.wait()
    if proc.returncode != 0:
        failure_class = "technical" if proc.returncode == 75 else "backend_failure"
        raise BackendExecutionError(failure_class, f"{backend} adapter failed")
    if not out.is_file() or out.stat().st_size < 16:
        raise BackendExecutionError("technical", f"{backend} adapter produced no MP4")
    return out, {
        "wall_time_sec": round(time.monotonic() - started, 3),
        "peak_vram_mib": peak,
    }


def _probe_mp4(path: Path) -> dict[str, Any]:
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
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        payload = json.loads(proc.stdout)
        stream = (payload.get("streams") or [])[0]
        duration = float((payload.get("format") or {}).get("duration") or 0)
        numerator, denominator = str(stream.get("avg_frame_rate") or "0/1").split("/", 1)
        fps = float(numerator) / max(float(denominator), 1.0)
    except (
        OSError,
        ValueError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
        IndexError,
    ) as exc:
        raise BackendExecutionError("technical", "generated MP4 failed ffprobe") from exc
    if duration <= 0 or fps <= 0 or int(stream.get("width") or 0) <= 0:
        raise BackendExecutionError("technical", "generated MP4 has invalid metadata")
    return {
        "duration": duration,
        "fps": fps,
        "video_codec": stream.get("codec_name"),
        "width": stream.get("width"),
        "height": stream.get("height"),
        "frames": stream.get("nb_frames"),
    }


async def _execute(job_id: str) -> None:
    state = jobs[job_id]
    async with gpu_lock:
        state["status"] = "running"
        _persist_job(job_id)
        video = Path(state["video_path"])
        audio = Path(state["audio_path"])
        job_dir = JOBS_ROOT / job_id
        candidate = job_dir / "candidate.partial.mp4"
        chosen = state["requested_backend"]
        fallback_reason: dict[str, Any] | None = None
        metrics: dict[str, Any]
        try:
            if (
                _sha256(video) != state["input_video_sha256"]
                or _sha256(audio) != state["input_audio_sha256"]
            ):
                raise BackendExecutionError("integrity", "input integrity check failed")
            try:
                candidate, metrics = await asyncio.to_thread(
                    _run_backend,
                    chosen,
                    video,
                    audio,
                    candidate,
                    state["parameters"],
                )
            except BackendExecutionError as first_error:
                fallback = state.get("fallback_backend")
                if (
                    not fallback
                    or fallback == chosen
                    or not _may_fallback(first_error.failure_class)
                    or not _backend_info(fallback)["technical_ready"]
                ):
                    raise
                fallback_reason = {
                    "from_backend": chosen,
                    "failure_class": first_error.failure_class,
                    "message": first_error.safe_message,
                }
                candidate.unlink(missing_ok=True)
                chosen = fallback
                candidate, metrics = await asyncio.to_thread(
                    _run_backend,
                    chosen,
                    video,
                    audio,
                    candidate,
                    state["parameters"],
                )
            probe = await asyncio.to_thread(_probe_mp4, candidate)
            if candidate.is_symlink() or candidate.resolve().parent != job_dir.resolve():
                raise BackendExecutionError("integrity", "adapter output path is invalid")
            artifact = job_dir / "artifact.mp4"
            candidate.replace(artifact)
            backend = _backend_info(chosen)
            state.update(
                {
                    "status": "completed",
                    "chosen_backend": chosen,
                    "fallback_reason": fallback_reason,
                    "output_sha256": _sha256(artifact),
                    "ffprobe": probe,
                    "metrics": metrics,
                    "provenance": {
                        "model": backend.get("model"),
                        "checkpoint_sha256": backend.get("checkpoint_sha256"),
                        "repo_commit": backend.get("repo_commit"),
                        "measured": backend.get("measured"),
                        "runtime": _runtime(),
                    },
                    "artifact_path": str(artifact),
                }
            )
        except BackendExecutionError as exc:
            candidate.unlink(missing_ok=True)
            state.update(
                {
                    "status": "failed",
                    "failure": {
                        "failure_class": exc.failure_class,
                        "message": exc.safe_message,
                    },
                }
            )
        except Exception:
            candidate.unlink(missing_ok=True)
            state.update(
                {
                    "status": "failed",
                    "failure": {
                        "failure_class": "unknown",
                        "message": "unexpected node failure",
                    },
                }
            )
        _persist_job(job_id)


async def _store_upload(upload: UploadFile, path: Path, limit: int) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    candidate = path.with_suffix(f"{path.suffix}.partial")
    digest = hashlib.sha256()
    total = 0
    try:
        with candidate.open("xb") as handle:
            while chunk := await upload.read(1024 * 1024):
                total += len(chunk)
                if total > limit:
                    raise HTTPException(status_code=413, detail="upload too large")
                digest.update(chunk)
                handle.write(chunk)
        if total == 0:
            raise HTTPException(status_code=400, detail="empty upload")
        candidate.replace(path)
    except Exception:
        candidate.unlink(missing_ok=True)
        raise
    return digest.hexdigest()


@app.get("/health")
def health(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    backends = {backend: _backend_info(backend) for backend in sorted(_BACKENDS)}
    return {
        "ok": True,
        "node": "private-windows-rtx-lipsync",
        "gpu": _gpu_health(),
        "queue": {
            "running": sum(state.get("status") == "running" for state in jobs.values()),
            "queued": sum(state.get("status") == "queued" for state in jobs.values()),
            "concurrency": 1,
        },
        "backends": backends,
        "runtime": _runtime(),
    }


@app.post("/v1/lipsync/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    video: UploadFile,
    audio: UploadFile,
    backend: str = Form(...),
    fallback_backend: str = Form(""),
    inference_steps: int = Form(20),
    guidance_scale: float = Form(1.5),
    deepcache: bool = Form(True),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _auth(authorization)
    if backend not in _BACKENDS or not _backend_info(backend, force_probe=True)["technical_ready"]:
        raise HTTPException(status_code=503, detail="requested backend is not ready")
    if fallback_backend and (
        fallback_backend not in _BACKENDS
        or fallback_backend == backend
        or not _backend_info(fallback_backend, force_probe=True)["technical_ready"]
    ):
        raise HTTPException(status_code=503, detail="fallback backend is not ready")
    if not 1 <= inference_steps <= 100 or not 0.1 <= guidance_scale <= 10:
        raise HTTPException(status_code=400, detail="invalid inference parameters")
    job_id = uuid.uuid4().hex
    job_dir = JOBS_ROOT / job_id
    video_path = job_dir / "input.mp4"
    audio_path = job_dir / "input.wav"
    video_hash = await _store_upload(video, video_path, _MAX_VIDEO_BYTES)
    try:
        audio_hash = await _store_upload(audio, audio_path, _MAX_AUDIO_BYTES)
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    jobs[job_id] = {
        "job_id": job_id,
        "status": "queued",
        "requested_backend": backend,
        "fallback_backend": fallback_backend or None,
        "video_path": str(video_path),
        "audio_path": str(audio_path),
        "input_video_sha256": video_hash,
        "input_audio_sha256": audio_hash,
        "parameters": {
            "inference_steps": inference_steps,
            "guidance_scale": guidance_scale,
            "deepcache": deepcache,
        },
    }
    _persist_job(job_id)
    background_tasks.add_task(_execute, job_id)
    return {"job_id": job_id, "status": "queued"}


@app.get("/v1/lipsync/jobs/{job_id}")
def get_job(
    job_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _auth(authorization)
    state = _load_job(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail="job not found")
    return _public_job(state)


@app.get("/v1/lipsync/jobs/{job_id}/artifact")
def get_artifact(
    job_id: str,
    authorization: str | None = Header(default=None),
) -> FileResponse:
    _auth(authorization)
    state = _load_job(job_id)
    if state is None or state.get("status") != "completed":
        raise HTTPException(status_code=404, detail="artifact not found")
    artifact = Path(str(state.get("artifact_path") or ""))
    expected = str(state.get("output_sha256") or "")
    if (
        artifact.is_symlink()
        or not artifact.is_file()
        or artifact.resolve().parent != (JOBS_ROOT / job_id).resolve()
        or _sha256(artifact) != expected
    ):
        raise HTTPException(status_code=409, detail="artifact integrity failure")
    return FileResponse(artifact, media_type="video/mp4", filename=f"{job_id}.mp4")


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("AIFILM_LIPSYNC_NODE_HOST", "127.0.0.1")
    port = int(os.environ.get("AIFILM_LIPSYNC_NODE_PORT", "8790"))
    uvicorn.run(app, host=host, port=port, log_level="info")
