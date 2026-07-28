#!/usr/bin/env python3
"""Private Windows/LAN audio-node service.

Start with: uvicorn audio_node_service:app --host <LAN-IP> --port 8788
Only Qwen TTS is built in. Music/SFX use explicit trusted argv adapters so the
control plane never guesses model-specific CLIs.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

ROOT = Path(os.environ.get("AIFILM_AUDIO_NODE_ROOT", r"C:\\aifilm-audio-node")).resolve()
JOBS = ROOT / "jobs"
TOKEN = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "")
MODEL = os.environ.get("AIFILM_AUDIO_NODE_QWEN_MODEL", "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
jobs: dict[str, dict[str, Any]] = {}
app = FastAPI(title="ai-film private audio node", docs_url=None, redoc_url=None)


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
        except ImportError:
            return False
    return bool(os.environ.get(f"AIFILM_AUDIO_NODE_{kind.upper()}_ARGV"))


@app.get("/health")
def health(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _auth(authorization)
    return {
        "ok": True,
        "node": "private-lan",
        "models": {kind: _available(kind) for kind in ("tts", "music", "sfx")},
        "model": MODEL,
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
    model = Qwen3TTSModel.from_pretrained(MODEL, device_map="cuda:0", dtype=torch.bfloat16)
    wavs, sr = (
        model.generate_voice_design(text=text, language=language, instruct=instruction)
        if "VoiceDesign" in MODEL
        else model.generate_custom_voice(
            text=text, language=language, speaker=voice, instruct=instruction
        )
    )
    raw = out.with_suffix(".raw.wav")
    sf.write(raw, wavs[0], sr)
    _normalize(raw, out)
    raw.unlink(missing_ok=True)


def _run_command(kind: str, payload: dict[str, Any], out: Path) -> None:
    raw = os.environ.get(f"AIFILM_AUDIO_NODE_{kind.upper()}_ARGV", "")
    if not raw:
        raise RuntimeError(f"{kind} model is not configured")
    template = json.loads(raw)
    if not isinstance(template, list) or not all(isinstance(item, str) for item in template):
        raise RuntimeError(f"{kind} argv is invalid")
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


async def _execute(job_id: str, kind: str, payload: dict[str, Any]) -> None:
    job = jobs[job_id]
    try:
        target = JOBS / f"{job_id}.wav"
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
        job.update({"status": "failed", "error": type(exc).__name__})


def _create(kind: str, payload: dict[str, Any]) -> dict[str, str]:
    if not _available(kind):
        raise HTTPException(503, f"{kind} model is unavailable")
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "queued", "kind": kind, "node": "private-lan"}
    asyncio.create_task(_execute(job_id, kind, payload))
    return {"job_id": job_id, "status": "queued"}


@app.post("/v1/{kind}")
def create(
    kind: str, payload: dict[str, Any], authorization: str | None = Header(default=None)
) -> dict[str, str]:
    _auth(authorization)
    if kind not in {"tts", "music", "sfx"}:
        raise HTTPException(404, "unknown audio kind")
    return _create(kind, payload)


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
