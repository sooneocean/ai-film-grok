#!/usr/bin/env python3
"""One auditable preparation boundary for every production audio track."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from audio_plan import build_audio_plan
from audio_timeline import VOCAL_TYPES, caption_bindings, validate_timeline
from audio_tts_manifest import AudioTTSManifestError, apply_measured_durations, build_tts_manifest
from scene_sound import reconcile
from util import read_json, write_json


class AudioProductionError(RuntimeError):
    pass


def _track_summary(timeline: dict[str, Any]) -> dict[str, dict[str, Any]]:
    events = timeline.get("events") if isinstance(timeline.get("events"), list) else []
    groups = {
        "tts": lambda event: event.get("type") in VOCAL_TYPES,
        "bgm": lambda event: event.get("type") in {"music", "performance"},
        "foley": lambda event: event.get("type") == "action_sfx",
        "ambience": lambda event: event.get("type") == "ambience",
    }
    return {
        name: {
            "event_count": sum(
                1 for event in events if isinstance(event, dict) and predicate(event)
            ),
            "event_ids": [
                event["id"]
                for event in events
                if isinstance(event, dict) and predicate(event) and isinstance(event.get("id"), str)
            ],
        }
        for name, predicate in groups.items()
    }


def _restore_rendered_tts(root: Path, previous_manifest: object) -> None:
    """Keep measured TTS only when the new job request is byte-for-byte identical."""
    if not isinstance(previous_manifest, dict):
        return
    previous_jobs = {
        str(job.get("audio_event_id")): job
        for job in previous_manifest.get("jobs") or []
        if isinstance(job, dict) and job.get("status") == "rendered"
    }
    if not previous_jobs:
        return
    timeline = read_json(root / "audio" / "audio-timeline.json")
    voice_cast = read_json(root / "audio" / "voice-cast.json")
    if not isinstance(timeline, dict) or not isinstance(voice_cast, dict):
        raise AudioProductionError("cannot restore rendered TTS without timeline and voice cast")
    fresh_manifest = build_tts_manifest(timeline, voice_cast)
    reusable = {
        str(job["audio_event_id"]): previous
        for job in fresh_manifest["jobs"]
        if isinstance(job, dict)
        and isinstance((previous := previous_jobs.get(str(job.get("audio_event_id")))), dict)
        and previous.get("request_sha256") == job.get("request_sha256")
        and isinstance(previous.get("actual_duration_sec"), (int, float))
    }
    if not reusable:
        return
    try:
        timeline = apply_measured_durations(
            timeline,
            {event_id: float(job["actual_duration_sec"]) for event_id, job in reusable.items()},
        )
    except AudioTTSManifestError as exc:
        raise AudioProductionError(f"cannot restore measured TTS duration: {exc}") from exc
    fresh_manifest = build_tts_manifest(timeline, voice_cast)
    for job in fresh_manifest["jobs"]:
        previous = reusable.get(str(job.get("audio_event_id")))
        if previous is None:
            continue
        job.update(
            {
                key: previous[key]
                for key in (
                    "status",
                    "actual_duration_sec",
                    "asset_sha256",
                    "tts",
                    "render_receipt",
                )
                if key in previous
            }
        )
    write_json(root / "audio" / "audio-timeline.json", timeline)
    write_json(root / "audio" / "caption-bindings.json", caption_bindings(timeline))
    write_json(root / "audio" / "tts-manifest.json", fresh_manifest)


def prepare_audio_production(root: Path, *, render_tts: bool = False) -> dict[str, Any]:
    """Compile all audio tracks into one receipt without generating asset candidates.

    Candidate generation and approval remain explicit commands.  This boundary
    only materializes the shared timeline, cast, caption bindings, and TTS job
    manifest; optional TTS rendering uses those already locked jobs.
    """
    root = Path(root).expanduser().resolve()
    if not (root / "film-spec.json").is_file():
        raise AudioProductionError("audio-produce requires film-spec.json")

    previous_manifest = read_json(root / "audio" / "tts-manifest.json")
    plan = build_audio_plan(
        root,
        compile_timeline=True,
        write_timeline=True,
        write_voice_cast=True,
        write_tts_manifest=True,
    )
    error = plan["audio_timeline"].get("error")
    if error:
        raise AudioProductionError(f"audio timeline cannot compile: {error}")
    _restore_rendered_tts(root, previous_manifest)
    timeline = read_json(root / "audio" / "audio-timeline.json")
    if not isinstance(timeline, dict):
        raise AudioProductionError("audio timeline was not written")
    try:
        validate_timeline(timeline)
    except Exception as exc:  # noqa: BLE001 - expose one public command error
        raise AudioProductionError(f"audio timeline is invalid: {exc}") from exc

    if render_tts:
        from audio_tts_render import AudioTTSRenderError, render_tts_events

        try:
            tts_render = render_tts_events(root)
        except AudioTTSRenderError as exc:
            raise AudioProductionError(str(exc)) from exc
        timeline = read_json(root / "audio" / "audio-timeline.json")
    else:
        tts_render = None

    scene_sound = reconcile(root, write=True)
    manifest = read_json(root / "audio" / "tts-manifest.json") or {}
    tracks = _track_summary(timeline)
    tts_jobs = manifest.get("jobs") if isinstance(manifest, dict) else []
    rendered = sum(
        1 for job in tts_jobs if isinstance(job, dict) and job.get("status") == "rendered"
    )
    tts_ready = rendered == tracks["tts"]["event_count"]
    scene_ready = scene_sound.get("status") != "blocked"
    report = {
        "schema_version": 1,
        "kind": "aifilm-audio-production",
        "root": str(root),
        "timeline": {
            "path": str(root / "audio" / "audio-timeline.json"),
            "event_count": len(timeline.get("events") or []),
            "sha256": manifest.get("timeline_sha256"),
        },
        "tracks": tracks,
        "artifacts": {
            "voice_cast": str(root / "audio" / "voice-cast.json"),
            "tts_manifest": str(root / "audio" / "tts-manifest.json"),
            "caption_bindings": str(root / "audio" / "caption-bindings.json"),
            "scene_sound_receipt": str(root / "receipts" / "scene-sound-status.json"),
        },
        "tts": {
            "rendered_jobs": rendered,
            "required_jobs": tracks["tts"]["event_count"],
            "ready": tts_ready,
            "rendered_this_run": tts_render is not None,
        },
        "scene_sound": scene_sound,
        "ready_for_final_mix": tts_ready and scene_ready,
        "required_next": (
            "final --root <film> (renders TTS/BGM/Foley/ambience stems into the final mix)"
            if tts_ready and scene_ready
            else (
                "resolve scene-sound blockers before final"
                if not scene_ready
                else "audio-produce --render-tts after reviewing the locked voice cast"
            )
        ),
        "candidate_policy": "BGM, Foley, and ambience candidates are never generated or approved here.",
    }
    target = root / "audio" / "production-plan.json"
    write_json(target, report)
    report["path"] = str(target)
    return report
