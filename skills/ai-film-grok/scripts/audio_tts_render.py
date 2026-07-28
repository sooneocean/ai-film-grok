#!/usr/bin/env python3
"""Render provenance-bound TTS assets for every vocal audio-timeline event."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from audio_timeline import caption_bindings
from audio_tts_manifest import AudioTTSManifestError, apply_measured_durations
from tts_backend import synthesize
from util import read_json, write_json


class AudioTTSRenderError(RuntimeError):
    pass


def _duration(path: Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        check=False,
        text=True,
    )
    if proc.returncode:
        raise AudioTTSRenderError(f"cannot probe TTS asset: {path.name}")
    try:
        value = float(json.loads(proc.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AudioTTSRenderError(f"cannot read TTS duration: {path.name}") from exc
    if value <= 0:
        raise AudioTTSRenderError(f"TTS asset is silent: {path.name}")
    return value


def render_tts_events(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    audio_dir = root / "audio"
    timeline = read_json(audio_dir / "audio-timeline.json")
    manifest = read_json(audio_dir / "tts-manifest.json")
    if not isinstance(timeline, dict) or not isinstance(manifest, dict):
        raise AudioTTSRenderError("audio-timeline.json and tts-manifest.json are required")
    jobs = manifest.get("jobs")
    if not isinstance(jobs, list):
        raise AudioTTSRenderError("tts-manifest jobs are required")
    actual: dict[str, float] = {}
    for job in jobs:
        if not isinstance(job, dict):
            raise AudioTTSRenderError("tts-manifest job must be an object")
        event_id = str(job.get("audio_event_id") or "")
        if not event_id:
            raise AudioTTSRenderError("tts-manifest job requires audio_event_id")
        if str(job.get("provider") or "") != "edge":
            raise AudioTTSRenderError(
                f"{event_id}: provider {job.get('provider')} requires an explicit adapter"
            )
        relative = Path(str(job.get("asset_path") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise AudioTTSRenderError(f"{event_id}: unsafe asset path")
        wav = root / relative
        mp3 = wav.with_suffix(".mp3")
        wav.parent.mkdir(parents=True, exist_ok=True)
        try:
            meta = synthesize(
                str(job["text"]),
                mp3,
                backend="edge",
                voice=str(job["voice_id"]),
                rate=str(job.get("rate") or "+0%"),
                pitch=str(job.get("pitch") or "+0Hz"),
                allow_network_fallback=False,
                usage_root=root,
                shot_id=str(job.get("shot_id") or ""),
                job_id=event_id,
                performance=job.get("performance_cue")
                if isinstance(job.get("performance_cue"), dict)
                else None,
            )
        except Exception as exc:  # noqa: BLE001 - preserve a single explicit job failure
            raise AudioTTSRenderError(
                f"{event_id}: TTS failed without provider fallback: {exc}"
            ) from exc
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(mp3),
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(wav),
            ],
            capture_output=True,
            check=False,
            text=True,
        )
        if proc.returncode or not wav.is_file():
            raise AudioTTSRenderError(f"{event_id}: cannot convert synthesized audio to WAV")
        duration = _duration(wav)
        actual[event_id] = duration
        job.update(
            {
                "status": "rendered",
                "actual_duration_sec": round(duration, 3),
                "asset_sha256": hashlib.sha256(wav.read_bytes()).hexdigest(),
                "tts": meta,
            }
        )
    try:
        updated = apply_measured_durations(timeline, actual)
    except AudioTTSManifestError as exc:
        raise AudioTTSRenderError(str(exc)) from exc
    write_json(audio_dir / "audio-timeline.json", updated)
    write_json(audio_dir / "caption-bindings.json", caption_bindings(updated))
    write_json(audio_dir / "tts-manifest.json", manifest)
    return {"ok": True, "job_count": len(jobs), "actual_duration_sec": actual}
