#!/usr/bin/env python3
"""Versioned, auditable audio timeline contracts.

This module is deliberately renderer-neutral.  It turns legacy shot fields and
the additive ``audio_cues`` surface into one absolute-time contract that can be
validated before any TTS or FFmpeg work begins.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
EVENT_TYPES = frozenset(
    {
        "dialogue",
        "inner_voice",
        "media_voice",
        "narration",
        "action_sfx",
        "ambience",
        "music",
        "silence",
    }
)
VOCAL_TYPES = frozenset({"dialogue", "inner_voice", "media_voice", "narration"})
ASSET_TYPES = frozenset({"action_sfx", "ambience", "music"})
SILENCE_SCOPES = frozenset({"bed", "music", "native", "sfx", "scene_sound"})
_CUE_MAP = {
    "foley": "action_sfx",
    "sfx": "action_sfx",
    "ambience": "ambience",
    "music": "music",
    "silence": "silence",
    "dialogue": "dialogue",
    "inner_monologue": "inner_voice",
    "phone_broadcast": "media_voice",
    "narration": "narration",
}


class AudioTimelineError(ValueError):
    pass


def _number(value: object, field: str, low: float = 0.0) -> float:
    if isinstance(value, bool):
        raise AudioTimelineError(f"{field} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise AudioTimelineError(f"{field} must be a number") from exc
    if result < low:
        raise AudioTimelineError(f"{field} must be >= {low}")
    return result


def _event_id(shot_id: str, index: int, event_type: str, start: float, text: str = "") -> str:
    raw = f"{shot_id}|{index}|{event_type}|{start:.3f}|{text}".encode()
    return f"aud_{shot_id}_{index:02d}_{hashlib.sha256(raw).hexdigest()[:10]}"


def _flatten(spec: dict[str, Any]) -> list[dict[str, Any]]:
    shots = [x for x in spec.get("shots") or [] if isinstance(x, dict)]
    if shots:
        return shots
    return [
        shot
        for scene in spec.get("scenes") or []
        if isinstance(scene, dict)
        for shot in scene.get("shots") or []
        if isinstance(shot, dict)
    ]


def _source_ok(source: str) -> bool:
    return source.startswith("https://") or source.startswith("local:") or "://" not in source


def compile_timeline(spec: dict[str, Any]) -> dict[str, Any]:
    """Compile the v1 timeline without mutating the film spec."""
    events: list[dict[str, Any]] = []
    cursor = 0.0
    for shot_index, shot in enumerate(_flatten(spec)):
        sid = str(shot.get("id") or shot.get("shot_id") or f"shot_{shot_index + 1:03d}")
        duration = _number(shot.get("duration_sec", 0), f"{sid}.duration_sec", 0.001)
        raw_cues = shot.get("audio_cues")
        if isinstance(raw_cues, list):
            for cue_index, cue in enumerate(raw_cues):
                if not isinstance(cue, dict):
                    continue
                kind = str(cue.get("kind") or "").strip().lower()
                event_type = (
                    _CUE_MAP.get(str(cue.get("line_type") or "").lower())
                    if kind == "voice"
                    else _CUE_MAP.get(kind)
                )
                if not event_type:
                    continue
                start = cursor + _number(
                    cue.get("start_offset_sec", 0),
                    f"{sid}.audio_cues[{cue_index}].start_offset_sec",
                )
                event_duration = _number(
                    cue.get("duration_sec", 0), f"{sid}.audio_cues[{cue_index}].duration_sec", 0.001
                )
                if start - cursor + event_duration > duration + 1e-6:
                    raise AudioTimelineError(
                        f"{sid}.audio_cues[{cue_index}] exceeds shot duration_sec"
                    )
                text = str(cue.get("spoken_text") or "").strip()
                event: dict[str, Any] = {
                    "id": _event_id(sid, cue_index, event_type, start, text),
                    "shot_id": sid,
                    "cue_index": cue_index,
                    "start_offset_sec": round(start - cursor, 3),
                    "type": event_type,
                    "start_sec": round(start, 3),
                    "duration_sec": round(event_duration, 3),
                    "gain": float(cue.get("gain", 1.0)),
                    "pan": float(cue.get("pan", 0.0)),
                    "fade_in_sec": float(cue.get("fade_in_sec", 0.0)),
                    "fade_out_sec": float(cue.get("fade_out_sec", 0.0)),
                    "muted": bool(cue.get("muted", False)),
                    "locked": bool(cue.get("locked", False)),
                }
                if event_type in VOCAL_TYPES:
                    event.update(
                        {
                            "speaker": str(cue.get("speaker") or ""),
                            "text": text,
                            "caption_text": str(cue.get("caption_text") or text),
                            "performance_cue": cue.get("performance")
                            or cue.get("performance_cue")
                            or {},
                        }
                    )
                if event_type in ASSET_TYPES:
                    event.update(
                        {
                            "asset": str(cue.get("asset") or cue.get("asset_hint") or ""),
                            "track": kind,
                            "source": str(cue.get("source") or ""),
                            "license": str(cue.get("license") or ""),
                            "source_sha256": str(cue.get("source_sha256") or ""),
                        }
                    )
                if event_type == "silence":
                    event["silence_scope"] = str(cue.get("silence_scope") or "bed")
                if cue.get("overlap_policy") is not None:
                    event["overlap_policy"] = str(cue["overlap_policy"])
                events.append(event)
        else:
            # Compatibility projection: legacy text remains narration/dialogue only.
            text = str(
                shot.get("nar") or shot.get("narration") or shot.get("dialogue") or ""
            ).strip()
            if text:
                event_type = "dialogue" if shot.get("speaker") else "narration"
                events.append(
                    {
                        "id": _event_id(sid, 0, event_type, cursor, text),
                        "shot_id": sid,
                        "cue_index": 0,
                        "start_offset_sec": 0.0,
                        "type": event_type,
                        "start_sec": round(cursor, 3),
                        "duration_sec": round(duration, 3),
                        "speaker": str(shot.get("speaker") or "narrator"),
                        "text": text,
                        "caption_text": text,
                        "performance_cue": shot.get("performance_cue") or {},
                        "gain": 1.0,
                        "pan": 0.0,
                        "fade_in_sec": 0.0,
                        "fade_out_sec": 0.0,
                        "muted": False,
                        "locked": False,
                    }
                )
        cursor += duration
    timeline = {
        "schema_version": SCHEMA_VERSION,
        "kind": "audio-timeline",
        "mode": str(spec.get("audio_style") or "drama_radio"),
        "events": events,
        "duration_sec": round(cursor, 3),
    }
    validate_timeline(timeline)
    return timeline


def validate_timeline(timeline: dict[str, Any]) -> dict[str, Any]:
    if timeline.get("schema_version") != SCHEMA_VERSION or timeline.get("kind") != "audio-timeline":
        raise AudioTimelineError(
            "audio-timeline schema_version=1 and kind=audio-timeline are required"
        )
    events = timeline.get("events")
    if not isinstance(events, list):
        raise AudioTimelineError("audio-timeline.events must be an array")
    seen: set[str] = set()
    vocal: list[dict[str, Any]] = []
    silences: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        prefix = f"audio-timeline.events[{index}]"
        if not isinstance(event, dict):
            raise AudioTimelineError(f"{prefix} must be an object")
        eid, event_type = str(event.get("id") or ""), str(event.get("type") or "")
        if not eid or eid in seen:
            raise AudioTimelineError(f"{prefix}.id must be unique")
        seen.add(eid)
        if event_type not in EVENT_TYPES:
            raise AudioTimelineError(f"{prefix}.type invalid")
        start, duration = (
            _number(event.get("start_sec"), f"{prefix}.start_sec"),
            _number(event.get("duration_sec"), f"{prefix}.duration_sec", 0.001),
        )
        if not str(event.get("shot_id") or ""):
            raise AudioTimelineError(f"{prefix}.shot_id is required")
        _number(event.get("gain", 0), f"{prefix}.gain")
        _number(event.get("pan", 0), f"{prefix}.pan", -1.0)
        for field in ("fade_in_sec", "fade_out_sec"):
            if _number(event.get(field, 0), f"{prefix}.{field}") > duration + 1e-6:
                raise AudioTimelineError(f"{prefix}.{field} cannot exceed duration_sec")
        if abs(float(event.get("pan", 0))) > 1:
            raise AudioTimelineError(f"{prefix}.pan must be between -1 and 1")
        if event_type in VOCAL_TYPES:
            if not str(event.get("speaker") or "") or not str(event.get("text") or "").strip():
                raise AudioTimelineError(f"{prefix} vocal event needs speaker and text")
            vocal.append({**event, "_start": start, "_end": start + duration})
        elif event_type == "silence":
            scope = str(event.get("silence_scope") or "bed")
            if scope not in SILENCE_SCOPES:
                raise AudioTimelineError(f"{prefix}.silence_scope is invalid")
            silences.append({**event, "_start": start, "_end": start + duration})
        elif event.get("text") or event.get("spoken_text"):
            raise AudioTimelineError(f"{prefix} non-vocal event must not contain TTS text")
        if event_type in ASSET_TYPES and not bool(event.get("muted")):
            source = str(event.get("source") or event.get("asset") or "")
            if not source or not _source_ok(source):
                raise AudioTimelineError(f"{prefix} asset must be local: or HTTPS")
            if not str(event.get("license") or "").strip():
                raise AudioTimelineError(f"{prefix} asset license is required")
            if not str(event.get("source_sha256") or "").strip():
                raise AudioTimelineError(f"{prefix} asset source_sha256 is required")
    for i, left in enumerate(vocal):
        for right in vocal[i + 1 :]:
            if left["_start"] < right["_end"] and right["_start"] < left["_end"]:
                allowed = {
                    str(left.get("overlap_policy") or ""),
                    str(right.get("overlap_policy") or ""),
                }
                if not allowed & {"interrupt", "cross_talk"}:
                    raise AudioTimelineError(
                        f"vocal overlap {left['id']} / {right['id']} requires interrupt or cross_talk"
                    )
    for silence in silences:
        for voice in vocal:
            if silence["_start"] < voice["_end"] and voice["_start"] < silence["_end"]:
                raise AudioTimelineError(
                    f"silence event {silence['id']} overlaps vocal event {voice['id']}"
                )
    _validate_style(str(timeline.get("mode") or "drama_radio"), vocal)
    return {
        "ok": True,
        "event_count": len(events),
        "vocal_event_count": len(vocal),
        "timeline_sha256": timeline_hash(timeline),
    }


def _validate_style(mode: str, vocal: Iterable[dict[str, Any]]) -> None:
    rows = list(vocal)
    total = sum(float(row["_end"] - row["_start"]) for row in rows) or 0.0
    narration = sum(
        float(row["_end"] - row["_start"]) for row in rows if row.get("type") == "narration"
    )
    if mode == "immersive_theatre" and narration:
        raise AudioTimelineError("immersive_theatre forbids narration events")
    if mode == "drama_radio" and total and narration / total > 0.25 + 1e-6:
        raise AudioTimelineError("drama_radio narration exceeds 25% of vocal duration")
    if mode == "audiobook" and total and narration / total < 0.50 - 1e-6:
        raise AudioTimelineError("audiobook narration must be at least 50% of vocal duration")


def timeline_hash(timeline: dict[str, Any]) -> str:
    canonical = json.dumps(timeline, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def rebase_to_rendered_shots(
    timeline: dict[str, Any],
    shot_starts: dict[str, float],
    *,
    shot_durations: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Return a copy whose event starts follow the rendered shot timeline."""
    validate_timeline(timeline)
    rebased = deepcopy(timeline)
    for event in rebased["events"]:
        shot_id = str(event.get("shot_id") or "")
        if shot_id not in shot_starts:
            raise AudioTimelineError(
                f"event {event['id']} references unknown rendered shot {shot_id}"
            )
        if shot_durations is not None:
            if shot_id not in shot_durations:
                raise AudioTimelineError(
                    f"event {event['id']} references unknown rendered shot duration {shot_id}"
                )
            offset = _number(
                event.get("start_offset_sec", 0), f"event {event['id']}.start_offset_sec"
            )
            duration = _number(
                event.get("duration_sec"), f"event {event['id']}.duration_sec", 0.001
            )
            if offset + duration > float(shot_durations[shot_id]) + 1e-6:
                raise AudioTimelineError(
                    f"event {event['id']} exceeds rendered shot duration {shot_id}"
                )
        event["start_sec"] = round(
            float(shot_starts[shot_id]) + float(event.get("start_offset_sec", 0.0)), 3
        )
    return rebased


def caption_bindings(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    """Return one subtitle source per spoken event; splitting happens downstream."""
    validate_timeline(timeline)
    return [
        {
            "audio_event_id": event["id"],
            "text_sha256": hashlib.sha256(
                str(event.get("caption_text") or event["text"]).encode("utf-8")
            ).hexdigest(),
            "start_sec": event["start_sec"],
            "end_sec": round(float(event["start_sec"]) + float(event["duration_sec"]), 3),
            "caption_text": event.get("caption_text") or event["text"],
        }
        for event in timeline["events"]
        if event.get("type") in VOCAL_TYPES and not event.get("muted")
    ]


def build_mix_execution_plan(
    timeline: dict[str, Any], *, sample_rate: int = 48000
) -> dict[str, Any]:
    """Compile timeline controls into an FFmpeg-ready, URL-free mix receipt."""
    validate_timeline(timeline)
    if sample_rate not in {44100, 48000}:
        raise AudioTimelineError("mix sample_rate must be 44100 or 48000")
    lanes: list[dict[str, Any]] = []
    duck_triggers: list[str] = []
    for event in timeline["events"]:
        if event.get("muted"):
            continue
        event_type = str(event["type"])
        pan = float(event.get("pan", 0.0))
        left, right = round((1.0 - pan) / 2.0, 4), round((1.0 + pan) / 2.0, 4)
        delay_ms = int(round(float(event["start_sec"]) * 1000))
        filters = [f"adelay={delay_ms}|{delay_ms}"]
        if float(event.get("fade_in_sec", 0)):
            filters.append(f"afade=t=in:st=0:d={float(event['fade_in_sec']):.3f}")
        if float(event.get("fade_out_sec", 0)):
            end = max(0.0, float(event["duration_sec"]) - float(event["fade_out_sec"]))
            filters.append(f"afade=t=out:st={end:.3f}:d={float(event['fade_out_sec']):.3f}")
        if event_type == "inner_voice":
            filters.append("highpass=f=250,lowpass=f=3200")
        filters.extend(
            [
                f"volume={float(event.get('gain', 1.0)):.3f}",
                f"pan=stereo|c0={left:.4f}*c0|c1={right:.4f}*c1",
            ]
        )
        source_kind = (
            "tts"
            if event_type in VOCAL_TYPES
            else ("asset" if event_type in ASSET_TYPES else "silence")
        )
        lane = {
            "audio_event_id": event["id"],
            "type": event_type,
            "source_kind": source_kind,
            "start_sec": event["start_sec"],
            "duration_sec": event["duration_sec"],
            "filters": filters,
        }
        if source_kind == "asset":
            lane["source_sha256"] = event["source_sha256"]
        lanes.append(lane)
        if event_type in VOCAL_TYPES:
            duck_triggers.append(event["id"])
    return {
        "schema_version": 1,
        "kind": "audio-mix-execution-plan",
        "sample_rate": sample_rate,
        "channel_layout": "stereo",
        "voice_target_lufs": -18.0,
        "voice_peak_db": -2.0,
        "final_limiter": 0.95,
        "ducking": {"trigger_event_ids": duck_triggers, "release_ms": 550},
        "silence_windows": [
            {
                "audio_event_id": event["id"],
                "start_sec": event["start_sec"],
                "end_sec": round(float(event["start_sec"]) + float(event["duration_sec"]), 3),
                "scope": event.get("silence_scope") or "bed",
            }
            for event in timeline["events"]
            if event.get("type") == "silence" and not event.get("muted")
        ],
        "lanes": lanes,
    }


def write_timeline(root: Path, timeline: dict[str, Any], *, out: Path | None = None) -> Path:
    target = out or root / "audio" / "audio-timeline.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(timeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
