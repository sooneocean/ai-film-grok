#!/usr/bin/env python3
"""Safe, auditable edits to an existing audio-timeline event."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from audio_timeline import VOCAL_TYPES, caption_bindings, validate_timeline


class AudioEventEditError(ValueError):
    pass


def edit_event(
    timeline: dict[str, Any],
    event_id: str,
    updates: dict[str, Any],
    *,
    force_locked: bool = False,
    tts_manifest: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, list[dict[str, Any]]]:
    """Apply allowed controls and mark TTS stale when its spoken contract changes."""
    validate_timeline(timeline)
    updated = deepcopy(timeline)
    event = next((row for row in updated["events"] if row.get("id") == event_id), None)
    if not isinstance(event, dict):
        raise AudioEventEditError(f"audio event not found: {event_id}")
    if event.get("locked") and not force_locked:
        raise AudioEventEditError(f"{event_id} is locked; use force_locked to edit")
    allowed = {
        "gain",
        "pan",
        "fade_in_sec",
        "fade_out_sec",
        "muted",
        "locked",
        "overlap_policy",
        "text",
        "caption_text",
        "performance_cue",
    }
    unknown = sorted(set(updates) - allowed)
    if unknown:
        raise AudioEventEditError(f"unsupported audio event fields: {', '.join(unknown)}")
    if (
        any(key in updates for key in ("text", "caption_text", "performance_cue"))
        and event.get("type") not in VOCAL_TYPES
    ):
        raise AudioEventEditError("non-vocal events cannot receive text or performance controls")
    event.update(updates)
    try:
        validate_timeline(updated)
    except Exception as exc:  # noqa: BLE001 - retain a command-facing edit error
        raise AudioEventEditError(str(exc)) from exc
    manifest = deepcopy(tts_manifest) if isinstance(tts_manifest, dict) else None
    if manifest is not None and any(key in updates for key in ("text", "performance_cue")):
        for job in manifest.get("jobs") or []:
            if isinstance(job, dict) and job.get("audio_event_id") == event_id:
                job["status"] = "stale"
                job["stale_reason"] = "event_text_or_performance_changed"
    return updated, manifest, caption_bindings(updated)
