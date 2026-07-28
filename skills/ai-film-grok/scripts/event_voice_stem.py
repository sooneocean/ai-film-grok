#!/usr/bin/env python3
"""Mix completed event-level TTS assets into one timeline-accurate voice stem."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from audio_timeline import VOCAL_TYPES, validate_timeline


class EventVoiceStemError(ValueError):
    pass


def _decode(path: Path, *, duration: float, inner_voice: bool, sample_rate: int) -> np.ndarray:
    filters = "highpass=f=250,lowpass=f=3200" if inner_voice else "anull"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-t",
            f"{duration:.3f}",
            "-af",
            filters,
            "-ar",
            str(sample_rate),
            "-ac",
            "2",
            "-f",
            "f32le",
            "pipe:1",
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        raise EventVoiceStemError(f"cannot decode TTS asset: {path.name}")
    raw = np.frombuffer(proc.stdout, dtype=np.float32)
    return raw.reshape((-1, 2)) if len(raw) else np.zeros((0, 2), dtype=np.float32)


def _controls(samples: np.ndarray, event: dict[str, Any], sample_rate: int) -> np.ndarray:
    out = samples.astype(np.float32, copy=True) * float(event.get("gain", 1.0))
    pan = float(event.get("pan", 0.0))
    out[:, 0] *= (1.0 - pan) / 2.0
    out[:, 1] *= (1.0 + pan) / 2.0
    for key, reverse in (("fade_in_sec", False), ("fade_out_sec", True)):
        count = min(len(out), int(round(float(event.get(key, 0.0)) * sample_rate)))
        if count:
            ramp = np.linspace(0.0, 1.0, count, dtype=np.float32)
            out[:count] *= ramp[:, None] if not reverse else 1.0
            if reverse:
                out[-count:] *= ramp[::-1, None]
    return out


def render_event_voice_stem(
    root: Path,
    timeline: dict[str, Any],
    manifest: dict[str, Any],
    *,
    duration_sec: float,
    out: Path,
) -> dict[str, Any]:
    validate_timeline(timeline)
    sample_rate = 48000
    jobs = {
        str(job.get("audio_event_id")): job
        for job in manifest.get("jobs") or []
        if isinstance(job, dict)
    }
    samples = np.zeros((max(1, int(round(duration_sec * sample_rate))), 2), dtype=np.float32)
    executed: list[str] = []
    for event in timeline["events"]:
        if event.get("type") not in VOCAL_TYPES or event.get("muted"):
            continue
        event_id = str(event["id"])
        job = jobs.get(event_id)
        if not job or job.get("status") != "rendered":
            raise EventVoiceStemError(f"{event_id}: completed event TTS asset is required")
        relative = Path(str(job.get("asset_path") or ""))
        asset = (root / relative).resolve()
        if relative.is_absolute() or ".." in relative.parts or not asset.is_file():
            raise EventVoiceStemError(f"{event_id}: TTS asset is missing or unsafe")
        if job.get("asset_sha256") != hashlib.sha256(asset.read_bytes()).hexdigest():
            raise EventVoiceStemError(f"{event_id}: TTS asset checksum changed")
        decoded = _decode(
            asset,
            duration=float(event["duration_sec"]),
            inner_voice=event.get("type") == "inner_voice",
            sample_rate=sample_rate,
        )
        start = max(0, int(round(float(event["start_sec"]) * sample_rate)))
        end = min(len(samples), start + len(decoded))
        if end > start:
            samples[start:end] += _controls(decoded[: end - start], event, sample_rate)
        executed.append(event_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "f32le",
            "-ar",
            str(sample_rate),
            "-ac",
            "2",
            "-i",
            "pipe:0",
            "-c:a",
            "pcm_s16le",
            str(out),
        ],
        input=np.clip(samples, -1.0, 1.0).tobytes(),
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        raise EventVoiceStemError("cannot write event voice stem")
    return {
        "path": str(out),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "event_count": len(executed),
        "event_ids": executed,
    }
