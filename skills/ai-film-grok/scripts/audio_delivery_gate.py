#!/usr/bin/env python3
"""Fail-closed evidence gate for audio timeline deliveries."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from audio_timeline import caption_bindings, timeline_hash, validate_timeline


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _probe(path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode:
        return {"ok": False, "error": "ffprobe failed"}
    streams = json.loads(proc.stdout).get("streams") or []
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    return {"ok": bool(audio), "audio_streams": audio}


def build_delivery_report(
    *,
    timeline: dict[str, Any],
    tts_manifest: dict[str, Any],
    subtitle_bindings: list[dict[str, Any]],
    final_mp4: Path | None = None,
) -> dict[str, Any]:
    """Return auditable evidence; callers must treat ``ok=false`` as a hard failure."""
    errors: list[str] = []
    try:
        validate_timeline(timeline)
    except Exception as exc:  # noqa: BLE001 - delivery report must retain all blockers
        errors.append(str(exc))
    expected = (
        {item["audio_event_id"]: item for item in caption_bindings(timeline)} if not errors else {}
    )
    provided = {
        str(item.get("audio_event_id")): item
        for item in subtitle_bindings
        if isinstance(item, dict)
    }
    if set(expected) != set(provided):
        errors.append("subtitle bindings must match every unmuted vocal event exactly once")
    for event_id, expected_row in expected.items():
        row = provided.get(event_id) or {}
        if row.get("text_sha256") != expected_row["text_sha256"]:
            errors.append(f"{event_id}: subtitle text hash mismatch")
        if (
            row.get("start_sec") != expected_row["start_sec"]
            or row.get("end_sec") != expected_row["end_sec"]
        ):
            errors.append(f"{event_id}: subtitle window mismatch")
    jobs = tts_manifest.get("jobs") if isinstance(tts_manifest, dict) else None
    if not isinstance(jobs, list):
        errors.append("TTS manifest jobs are required")
        jobs = []
    for job in jobs:
        if not isinstance(job, dict) or not job.get("request_sha256"):
            errors.append("every TTS job requires request provenance")
            continue
        if job.get("status") not in {"ready", "rendered"}:
            errors.append(f"{job.get('audio_event_id')}: TTS asset is not ready")
    probe: dict[str, Any] | None = None
    if final_mp4 is not None:
        if not final_mp4.is_file():
            errors.append("final MP4 is missing")
        else:
            probe = _probe(final_mp4)
            if not probe.get("ok"):
                errors.append("final MP4 has no valid audio stream")
    return {
        "schema_version": 1,
        "kind": "audio-delivery-report",
        "ok": not errors,
        "errors": errors,
        "timeline_sha256": timeline_hash(timeline) if not errors else None,
        "tts_job_count": len(jobs),
        "subtitle_binding_count": len(subtitle_bindings),
        "final_mp4": {
            "path": str(final_mp4) if final_mp4 else None,
            "sha256": _sha256(final_mp4) if final_mp4 and final_mp4.is_file() else None,
            "ffprobe": probe,
        },
    }
