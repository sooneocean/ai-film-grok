#!/usr/bin/env python3
"""Event-level TTS provenance and measured-duration gates."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from audio_timeline import VOCAL_TYPES, AudioTimelineError, validate_timeline
from voice_cast_profiles import VoiceCastError, validate_event_language


class AudioTTSManifestError(ValueError):
    pass


def _fingerprint(event: dict[str, Any], profile: dict[str, Any]) -> str:
    payload = {
        "event_id": event["id"],
        "text": event["text"],
        "performance_cue": event.get("performance_cue") or {},
        "voice_profile_hash": profile.get("profile_hash"),
        "provider": profile.get("provider"),
        "voice_id": profile.get("voice_id"),
        "rate": profile.get("rate"),
        "pitch": profile.get("pitch"),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


def build_tts_manifest(timeline: dict[str, Any], voice_cast: dict[str, Any]) -> dict[str, Any]:
    """Build independent TTS jobs; non-vocal events can never enter this manifest."""
    validate_timeline(timeline)
    profiles = voice_cast.get("profiles") if isinstance(voice_cast, dict) else None
    if not isinstance(profiles, dict):
        raise AudioTTSManifestError("voice-cast profiles are required")
    jobs: list[dict[str, Any]] = []
    for event in timeline["events"]:
        if event.get("type") not in VOCAL_TYPES or event.get("muted"):
            continue
        speaker = str(event.get("speaker") or "")
        profile = profiles.get(speaker)
        if not isinstance(profile, dict):
            raise AudioTTSManifestError(f"{event['id']}: missing voice-cast profile for {speaker}")
        try:
            validate_event_language(event, profile)
        except VoiceCastError as exc:
            raise AudioTTSManifestError(str(exc)) from exc
        fingerprint = _fingerprint(event, profile)
        jobs.append(
            {
                "audio_event_id": event["id"],
                "shot_id": event["shot_id"],
                "speaker": speaker,
                "text": event["text"],
                "language": profile["language"],
                "provider": profile["provider"],
                "voice_id": profile["voice_id"],
                "rate": profile.get("rate", "+0%"),
                "pitch": profile.get("pitch", "+0Hz"),
                "performance_cue": event.get("performance_cue") or {},
                "reserved_start_sec": event["start_sec"],
                "reserved_duration_sec": event["duration_sec"],
                "request_sha256": fingerprint,
                "asset_path": f"audio/tts-events/{event['id']}.wav",
                "status": "pending",
            }
        )
    return {
        "schema_version": 1,
        "kind": "audio-tts-manifest",
        "timeline_sha256": hashlib.sha256(
            json.dumps(timeline, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "jobs": jobs,
    }


def apply_measured_durations(
    timeline: dict[str, Any], measured_duration_sec: dict[str, float]
) -> dict[str, Any]:
    """Write actual TTS durations back and reject window overruns or implicit crosstalk."""
    validate_timeline(timeline)
    updated = deepcopy(timeline)
    for event in updated["events"]:
        event_id = str(event["id"])
        if event.get("type") not in VOCAL_TYPES or event_id not in measured_duration_sec:
            continue
        duration = measured_duration_sec[event_id]
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
            raise AudioTTSManifestError(f"{event_id}: measured duration must be positive")
        reserved = float(event["duration_sec"])
        if float(duration) > reserved + 0.03:
            raise AudioTTSManifestError(
                f"{event_id}: actual TTS exceeds reserved window ({duration:.2f}s > {reserved:.2f}s)"
            )
        event["actual_duration_sec"] = round(float(duration), 3)
        event["duration_sec"] = round(float(duration), 3)
    try:
        validate_timeline(updated)
    except AudioTimelineError as exc:
        raise AudioTTSManifestError(str(exc)) from exc
    return updated
