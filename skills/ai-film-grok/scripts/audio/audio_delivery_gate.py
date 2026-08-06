#!/usr/bin/env python3
"""Fail-closed evidence gate for audio timeline deliveries."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from audio_timeline import caption_bindings, timeline_hash, validate_timeline
from util import sha256_file


def _probe(path: Path) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "ffprobe timed out"}
    if proc.returncode:
        return {"ok": False, "error": "ffprobe failed"}
    streams = json.loads(proc.stdout).get("streams") or []
    audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
    return {"ok": bool(audio), "audio_streams": audio}


def _verify_rendered_tts_asset(root: Path, job: dict[str, Any]) -> str | None:
    root = root.expanduser().resolve()
    relative = Path(str(job.get("asset_path") or ""))
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        return "rendered TTS asset path is missing or unsafe"
    asset = (root / relative).resolve()
    try:
        asset.relative_to(root)
    except ValueError:
        return "rendered TTS asset escapes film root"
    if not asset.is_file():
        return "rendered TTS asset is missing"
    if str(job.get("asset_sha256") or "") != sha256_file(asset):
        return "rendered TTS asset checksum changed"
    return None


def _verify_production_plan(
    plan: object,
    timeline: dict[str, Any],
    scene_sound_receipt: object,
) -> list[str]:
    """Bind delivery verification to the unified production-audio receipt."""
    if not isinstance(plan, dict) or plan.get("kind") != "aifilm-audio-production":
        return ["unified audio production receipt is required"]
    errors: list[str] = []
    current_hash = timeline_hash(timeline)
    receipt_hash = (plan.get("timeline") or {}).get("sha256")
    if receipt_hash != current_hash:
        errors.append("unified audio production receipt is stale for the current timeline")
    events = timeline.get("events") if isinstance(timeline.get("events"), list) else []
    expected = {
        "tts": sum(
            1
            for event in events
            if event.get("type") in {"dialogue", "inner_voice", "media_voice", "narration"}
        ),
        "bgm": sum(1 for event in events if event.get("type") in {"music", "performance"}),
        "foley": sum(1 for event in events if event.get("type") == "action_sfx"),
        "ambience": sum(1 for event in events if event.get("type") == "ambience"),
    }
    tracks = plan.get("tracks") if isinstance(plan.get("tracks"), dict) else {}
    for name, count in expected.items():
        if not isinstance(tracks.get(name), dict) or tracks[name].get("event_count") != count:
            errors.append(f"unified audio production receipt has stale {name} track coverage")
    if not isinstance(scene_sound_receipt, dict):
        errors.append("scene-sound receipt is required")
    else:
        plan_scene = plan.get("scene_sound") if isinstance(plan.get("scene_sound"), dict) else {}
        if plan_scene.get("source_projection_sha256") != scene_sound_receipt.get(
            "source_projection_sha256"
        ):
            errors.append("unified audio production receipt is stale for scene sound")
        if scene_sound_receipt.get("status") == "blocked":
            errors.append("scene-sound receipt has blocking events")
    return errors


def build_delivery_report(
    *,
    timeline: dict[str, Any],
    tts_manifest: dict[str, Any],
    subtitle_bindings: list[dict[str, Any]],
    final_mp4: Path | None = None,
    previous_report: dict[str, Any] | None = None,
    root: Path | None = None,
    audio_production: dict[str, Any] | None = None,
    scene_sound_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return auditable evidence; callers must treat ``ok=false`` as a hard failure."""
    errors: list[str] = []
    try:
        validate_timeline(timeline)
    except Exception as exc:  # noqa: BLE001 - delivery report must retain all blockers
        errors.append(str(exc))
    if audio_production is not None or scene_sound_receipt is not None:
        errors.extend(_verify_production_plan(audio_production, timeline, scene_sound_receipt))
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
        elif job.get("status") == "rendered":
            if root is None:
                errors.append(f"{job.get('audio_event_id')}: rendered TTS requires film root")
            else:
                error = _verify_rendered_tts_asset(root, job)
                if error:
                    errors.append(f"{job.get('audio_event_id')}: {error}")
    probe: dict[str, Any] | None = None
    if final_mp4 is not None:
        if not final_mp4.is_file():
            errors.append("final MP4 is missing")
        else:
            probe = _probe(final_mp4)
            if not probe.get("ok"):
                errors.append("final MP4 has no valid audio stream")
    current_timeline_sha256 = timeline_hash(timeline) if not errors else None
    previous_final = (previous_report or {}).get("final_mp4")
    previous_timeline_sha256 = (previous_report or {}).get("timeline_sha256")
    delivery_stale = bool(
        isinstance(previous_final, dict)
        and previous_final.get("sha256")
        and previous_timeline_sha256
        and current_timeline_sha256
        and previous_timeline_sha256 != current_timeline_sha256
    )
    if delivery_stale:
        errors.append("existing final delivery is stale because audio timeline changed")
    return {
        "schema_version": 1,
        "kind": "audio-delivery-report",
        "ok": not errors,
        "errors": errors,
        "timeline_sha256": current_timeline_sha256,
        "tts_job_count": len(jobs),
        "subtitle_binding_count": len(subtitle_bindings),
        "final_mp4": {
            "path": str(final_mp4) if final_mp4 else None,
            "sha256": sha256_file(final_mp4) if final_mp4 and final_mp4.is_file() else None,
            "ffprobe": probe,
        },
        "stale": delivery_stale,
        "stale_reason": "audio_timeline_changed" if delivery_stale else None,
        "production_receipt": {
            "required": audio_production is not None or scene_sound_receipt is not None,
            "ok": not any(error.startswith("unified audio production") for error in errors),
        },
    }
