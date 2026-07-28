#!/usr/bin/env python3
"""Private Windows/LAN audio-node service.

Start with: uvicorn audio_node_service:app --host <LAN-IP> --port 8788
Only Qwen TTS is built in. Music, SFX, and performance tracks use explicit
trusted argv adapters so the control plane never guesses model-specific CLIs.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import uuid
import wave
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse

ROOT = Path(os.environ.get("AIFILM_AUDIO_NODE_ROOT", r"C:\\aifilm-audio-node")).resolve()
JOBS = ROOT / "jobs"
REFERENCES = ROOT / "music-references"
TOKEN = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "")
MODEL_ID = os.environ.get("AIFILM_AUDIO_NODE_QWEN_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
MODEL_PATH = os.environ.get("AIFILM_AUDIO_NODE_QWEN_MODEL_PATH", MODEL_ID)
MUSIC_MODEL_ID = os.environ.get("AIFILM_AUDIO_NODE_MUSIC_MODEL", "ACE-Step-1.5")
MUSIC_CHECKPOINT_FINGERPRINT = os.environ.get(
    "AIFILM_AUDIO_NODE_MUSIC_CHECKPOINT_FINGERPRINT", "unknown"
)
jobs: dict[str, dict[str, Any]] = {}
AUDIO_KINDS = ("tts", "music", "sfx", "performance")
# All configured renderers use the same 5090.  Serializing execution prevents
# independently valid jobs from evicting each other's model weights or OOMing.
GPU_GENERATION_LOCK = asyncio.Lock()
app = FastAPI(title="ai-film private audio node", docs_url=None, redoc_url=None, openapi_url=None)


def _auth(value: str | None) -> None:
    if (
        not TOKEN
        or not value
        or not value.startswith("Bearer ")
        or not hmac.compare_digest(value[7:], TOKEN)
    ):
        raise HTTPException(401, "unauthorized")


def _available(kind: str) -> bool:
    if kind == "tts":
        try:
            import qwen_tts  # noqa: F401
            import soundfile  # noqa: F401
            import torch  # noqa: F401

            return True
        except Exception:
            return False
    try:
        _command_template(kind)
        return True
    except RuntimeError:
        return False


def _command_template(kind: str) -> list[str]:
    raw = os.environ.get(f"AIFILM_AUDIO_NODE_{kind.upper()}_ARGV", "")
    if not raw:
        raise RuntimeError(f"{kind} model is not configured")
    try:
        template = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{kind} argv is invalid") from exc
    if (
        not isinstance(template, list)
        or not template
        or not all(isinstance(item, str) for item in template)
    ):
        raise RuntimeError(f"{kind} argv is invalid")
    return template


def _music_batch_template() -> list[str]:
    raw = os.environ.get("AIFILM_AUDIO_NODE_MUSIC_BATCH_ARGV", "")
    if not raw:
        raise RuntimeError("music batch model is not configured")
    try:
        template = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("music batch argv is invalid") from exc
    if (
        not isinstance(template, list)
        or not template
        or not all(isinstance(item, str) for item in template)
    ):
        raise RuntimeError("music batch argv is invalid")
    return template


def _gpu_health() -> dict[str, Any]:
    """Report capacity only; never expose inputs, tokens, or filesystem paths."""
    try:
        import torch

        if not torch.cuda.is_available():
            return {"available": False}
        free, total = torch.cuda.mem_get_info(0)
        return {
            "available": True,
            "name": torch.cuda.get_device_name(0),
            "cuda": torch.version.cuda,
            "free_vram_mib": int(free // 1024**2),
            "total_vram_mib": int(total // 1024**2),
        }
    except Exception:
        return {"available": False}


@app.get("/health")
def health(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    return {
        "ok": True,
        "node": "private-lan",
        "models": {kind: _available(kind) for kind in AUDIO_KINDS},
        "music_batch": bool(os.environ.get("AIFILM_AUDIO_NODE_MUSIC_BATCH_ARGV", "").strip()),
        "model": MODEL_ID,
        "music_model": MUSIC_MODEL_ID,
        "music_checkpoint_fingerprint": MUSIC_CHECKPOINT_FINGERPRINT,
        "gpu": _gpu_health(),
    }


def _normalize(source: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-ar",
            "44100",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(out),
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )


def _store_music_reference(raw: bytes) -> dict[str, str]:
    if len(raw) < 512 or len(raw) > 64 * 1024 * 1024 or raw[:4] != b"RIFF":
        raise HTTPException(422, "invalid music reference WAV")
    source_hash = hashlib.sha256(raw).hexdigest()
    REFERENCES.mkdir(parents=True, exist_ok=True)
    source = REFERENCES / f".{uuid.uuid4().hex}.wav"
    target = REFERENCES / f"{source_hash}.wav"
    try:
        source.write_bytes(raw)
        with wave.open(str(source), "rb") as handle:
            if (
                handle.getnchannels() != 2
                or handle.getsampwidth() != 2
                or handle.getframerate() != 44100
                or handle.getnframes() <= 0
            ):
                raise HTTPException(422, "music reference must be 44.1kHz stereo PCM s16le")
        if not target.exists():
            source.replace(target)
    except Exception:
        source.unlink(missing_ok=True)
        raise
    source.unlink(missing_ok=True)
    return {"reference_id": source_hash, "source_sha256": source_hash}


@app.post("/v1/music-reference")
async def upload_music_reference(
    request: Request, authorization: str | None = Header(default=None)
) -> dict[str, str]:
    _auth(authorization)
    return _store_music_reference(await request.body())


def _run_tts(payload: dict[str, Any], out: Path) -> None:
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    text = str(payload.get("text") or "").strip()
    if not text or len(text) > 10000:
        raise ValueError("text must contain 1-10000 characters")
    voice = str(payload.get("voice_profile_id") or "Vivian")
    language = str(payload.get("language") or "Chinese")
    instruction = str((payload.get("performance") or {}).get("instruction") or "")[:1000]
    model = Qwen3TTSModel.from_pretrained(MODEL_PATH, device_map="cuda:0", dtype=torch.bfloat16)
    wavs, sr = (
        model.generate_voice_design(text=text, language=language, instruct=instruction)
        if "VoiceDesign" in MODEL_ID
        else model.generate_custom_voice(
            text=text, language=language, speaker=voice, instruct=instruction
        )
    )
    raw = out.with_suffix(".raw.wav")
    sf.write(raw, wavs[0], sr)
    _normalize(raw, out)
    raw.unlink(missing_ok=True)


def _run_command(kind: str, payload: dict[str, Any], out: Path) -> None:
    template = _command_template(kind)
    source = out.with_suffix(".source.wav")
    values = {
        "out": str(source),
        "prompt": str(payload.get("prompt") or ""),
        "duration": str(payload.get("duration") or 5),
        "seed": str(payload.get("seed") or 0),
    }
    command = [item.format(**values) for item in template]
    subprocess.run(command, check=True, capture_output=True, timeout=900)
    _normalize(source, out)
    source.unlink(missing_ok=True)


def _run_music_batch(payload: dict[str, Any], out_dir: Path) -> list[Path]:
    """Run one trusted ACE adapter with an ephemeral JSON request."""
    template = _music_batch_template()
    out_dir.mkdir(parents=True, exist_ok=True)
    request_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=out_dir.parent,
            prefix=".music-batch-",
            suffix=".json",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False)
            request_path = Path(handle.name)
        values = {"request_json": str(request_path), "out_dir": str(out_dir)}
        command = [item.format(**values) for item in template]
        subprocess.run(command, check=True, capture_output=True, timeout=1800)
    finally:
        if request_path is not None:
            request_path.unlink(missing_ok=True)

    batch_size = int(payload["batch_size"])
    generated = [out_dir / f"{index:02d}.wav" for index in range(batch_size)]
    if not all(path.is_file() for path in generated):
        raise RuntimeError("music batch adapter returned incomplete outputs")
    normalized: list[Path] = []
    for index, source in enumerate(generated):
        target = out_dir / f"{index:02d}.normalized.wav"
        _normalize(source, target)
        source.unlink(missing_ok=True)
        target.replace(source)
        normalized.append(source)
    return normalized


async def _execute(job_id: str, kind: str, payload: dict[str, Any]) -> None:
    job = jobs[job_id]
    target = JOBS / f"{job_id}.wav"
    try:
        JOBS.mkdir(parents=True, exist_ok=True)
        async with GPU_GENERATION_LOCK:
            job["status"] = "running"
            if kind == "tts":
                await asyncio.to_thread(_run_tts, payload, target)
            else:
                await asyncio.to_thread(_run_command, kind, payload, target)
        job.update(
            {
                "status": "completed",
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "path": str(target),
            }
        )
    except Exception as exc:
        target.unlink(missing_ok=True)
        target.with_suffix(".raw.wav").unlink(missing_ok=True)
        target.with_suffix(".source.wav").unlink(missing_ok=True)
        job.update({"status": "failed", "error": type(exc).__name__})


async def _execute_music_batch(job_id: str, payload: dict[str, Any]) -> None:
    job = jobs[job_id]
    target_dir = JOBS / job_id
    try:
        JOBS.mkdir(parents=True, exist_ok=True)
        async with GPU_GENERATION_LOCK:
            job["status"] = "running"
            paths = await asyncio.to_thread(_run_music_batch, payload, target_dir)
        seeds = [int(seed) for seed in payload["seeds"]]
        artifacts = [
            {
                "index": index,
                "seed": seeds[index],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for index, path in enumerate(paths)
        ]
        job.update(
            {
                "status": "completed",
                "model": MUSIC_MODEL_ID,
                "checkpoint_fingerprint": MUSIC_CHECKPOINT_FINGERPRINT,
                "artifacts": artifacts,
            }
        )
    except Exception as exc:
        if target_dir.is_dir():
            for path in target_dir.glob("*"):
                if path.is_file():
                    path.unlink(missing_ok=True)
            target_dir.rmdir()
        job.update({"status": "failed", "error": type(exc).__name__})


def _create(kind: str, payload: dict[str, Any]) -> dict[str, str]:
    if not _available(kind):
        raise HTTPException(503, f"{kind} model is unavailable")
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "queued", "kind": kind, "node": "private-lan"}
    asyncio.create_task(_execute(job_id, kind, payload))
    return {"job_id": job_id, "status": "queued"}


@app.post("/v1/{kind}")
async def create(
    kind: str, payload: dict[str, Any], authorization: str | None = Header(default=None)
) -> dict[str, str]:
    _auth(authorization)
    if kind == "music-batch":
        return await create_music_batch(payload, authorization)
    if kind not in AUDIO_KINDS:
        raise HTTPException(404, "unknown audio kind")
    return _create(kind, payload)


@app.post("/v1/music-batch")
async def create_music_batch(
    payload: dict[str, Any], authorization: str | None = Header(default=None)
) -> dict[str, str]:
    _auth(authorization)
    try:
        prompt = str(payload.get("prompt") or "").strip()
        batch_size = int(payload.get("batch_size") or 0)
        seeds = [int(seed) for seed in payload.get("seeds") or []]
        duration = float(payload.get("duration") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "invalid music batch request") from exc
    if not 1 <= len(prompt) <= 512:
        raise HTTPException(422, "prompt must contain 1-512 characters")
    if not 1 <= batch_size <= 8:
        raise HTTPException(422, "batch_size must be between 1 and 8")
    if len(seeds) != batch_size or len(set(seeds)) != batch_size:
        raise HTTPException(422, "seeds must contain one unique seed per batch item")
    if not 10 <= duration <= 600:
        raise HTTPException(422, "duration must be between 10 and 600 seconds")
    task_type = str(payload.get("task_type") or "text2music")
    if task_type not in {"text2music", "cover", "repaint"}:
        raise HTTPException(422, "invalid ACE-Step task type")
    payload = dict(payload)
    if task_type in {"cover", "repaint"}:
        reference_id = str(payload.pop("reference_audio_id", "") or "")
        reference_path = REFERENCES / f"{reference_id}.wav"
        if (
            len(reference_id) != 64
            or any(character not in "0123456789abcdef" for character in reference_id)
            or not reference_path.is_file()
        ):
            raise HTTPException(422, "cover/repaint requires an uploaded reference")
        payload["reference_audio"] = str(reference_path)
    else:
        payload.pop("reference_audio_id", None)
    try:
        _music_batch_template()
    except RuntimeError as exc:
        raise HTTPException(503, "music batch model is unavailable") from exc
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "queued", "kind": "music-batch", "node": "private-lan"}
    asyncio.create_task(_execute_music_batch(job_id, payload))
    return {"job_id": job_id, "status": "queued"}


@app.get("/v1/jobs/{job_id}")
def job(job_id: str, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    if job_id not in jobs:
        raise HTTPException(404, "job not found")
    return {key: value for key, value in jobs[job_id].items() if key not in {"path"}}


@app.get("/v1/jobs/{job_id}/audio")
def audio(job_id: str, authorization: str | None = Header(default=None)) -> FileResponse:
    _auth(authorization)
    job = jobs.get(job_id) or {}
    path = Path(str(job.get("path") or ""))
    if job.get("status") != "completed" or not path.is_file():
        raise HTTPException(409, "audio is not ready")
    return FileResponse(path, media_type="audio/wav", filename=f"{job_id}.wav")


@app.get("/v1/jobs/{job_id}/audio/{index}")
def batch_audio(
    job_id: str, index: int, authorization: str | None = Header(default=None)
) -> FileResponse:
    _auth(authorization)
    job = jobs.get(job_id) or {}
    artifacts = job.get("artifacts") if isinstance(job.get("artifacts"), list) else []
    if (
        job.get("status") != "completed"
        or index < 0
        or index >= len(artifacts)
        or int(artifacts[index].get("index", -1)) != index
    ):
        raise HTTPException(409, "batch audio is not ready")
    path = JOBS / job_id / f"{index:02d}.wav"
    if not path.is_file():
        raise HTTPException(409, "batch audio is not ready")
    return FileResponse(path, media_type="audio/wav", filename=f"{job_id}-{index:02d}.wav")
