#!/usr/bin/env python3
"""Render provenance-bound TTS assets for every vocal audio-timeline event."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from audio_timeline import caption_bindings, timeline_hash, validate_timeline
from audio_tts_manifest import AudioTTSManifestError, apply_measured_durations
from tts_backend import synthesize
from util import read_json, write_json


class AudioTTSRenderError(RuntimeError):
    pass


def _duration(path: Path) -> float:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioTTSRenderError(
            f"cannot probe TTS asset (ffprobe timed out): {path.name}"
        ) from exc
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
    try:
        validate_timeline(timeline)
    except Exception as exc:  # noqa: BLE001 - keep the renderer's public error boundary
        raise AudioTTSRenderError(f"invalid audio timeline: {exc}") from exc
    expected_timeline_hash = str(manifest.get("timeline_sha256") or "")
    if len(expected_timeline_hash) != 64:
        raise AudioTTSRenderError("tts-manifest requires a 64-character timeline hash")
    if expected_timeline_hash != timeline_hash(timeline):
        raise AudioTTSRenderError(
            "tts-manifest timeline hash does not match audio-timeline; rebuild the audio plan"
        )
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
        provider = str(job.get("provider") or "").strip().lower()
        # Locked providers that synthesize() already routes (一角一声 / no silent fallback).
        supported = {
            "edge",
            "grok",
            "mimo",
            "fish",
            "minimax",
            "voicebox",
            "qwen3",
            "external",
        }
        if provider not in supported:
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
                backend=provider,
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
        try:
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
                timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            raise AudioTTSRenderError(
                f"{event_id}: cannot convert synthesized audio to WAV (ffmpeg timed out)"
            ) from exc
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
                "render_receipt": {
                    "provider": str(meta.get("backend") or "edge"),
                    "model": meta.get("model"),
                    "voice": meta.get("voice") or str(job["voice_id"]),
                    "performance_hash": meta.get("performance_hash"),
                    "performance_compile": meta.get("performance_compile"),
                },
            }
        )
    try:
        updated = apply_measured_durations(timeline, actual)
    except AudioTTSManifestError as exc:
        raise AudioTTSRenderError(str(exc)) from exc
    write_json(audio_dir / "audio-timeline.json", updated)
    write_json(audio_dir / "caption-bindings.json", caption_bindings(updated))
    manifest["timeline_sha256"] = timeline_hash(updated)
    write_json(audio_dir / "tts-manifest.json", manifest)
    return {"ok": True, "job_count": len(jobs), "actual_duration_sec": actual}
