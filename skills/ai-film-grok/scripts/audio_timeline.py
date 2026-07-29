#!/usr/bin/env python3
"""Versioned, auditable audio timeline contracts.

This module is deliberately renderer-neutral.  It turns legacy shot fields and
the additive ``audio_cues`` surface into one absolute-time contract that can be
validated before any TTS or FFmpeg work begins.
"""

from __future__ import annotations

import hashlib
import json
import re
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
        "performance",
        "silence",
    }
)
VOCAL_TYPES = frozenset({"dialogue", "inner_voice", "media_voice", "narration"})
ASSET_TYPES = frozenset({"action_sfx", "ambience", "music", "performance"})
SILENCE_SCOPES = frozenset({"bed", "music", "native", "sfx", "scene_sound"})
_CUE_MAP = {
    "foley": "action_sfx",
    "sfx": "action_sfx",
    "ambience": "ambience",
    "music": "music",
    "performance": "performance",
    "silence": "silence",
    "dialogue": "dialogue",
    "inner_monologue": "inner_voice",
    "phone_broadcast": "media_voice",
    "narration": "narration",
}


class AudioTimelineError(ValueError):
    pass


def is_noncommercial_license(value: object) -> bool:
    normalized = re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())
    return "CCBYNC" in normalized


def is_candidate_only_license(value: object) -> bool:
    """Stable Audio Open is not cleared for formal production by its download gate."""
    return str(value or "").strip() == "Stability AI Community License"


def is_approved_internal_sfx(event: dict[str, Any], delivery_scope: str) -> bool:
    source = str(event.get("source") or event.get("asset") or "").replace("\\", "/")
    receipt = str(event.get("approval_receipt") or "").replace("\\", "/")
    return bool(
        event.get("type") == "action_sfx"
        and delivery_scope == "noncommercial_internal"
        and event.get("approval_status") == "approved_noncommercial"
        and event.get("production_eligible") is False
        and event.get("usage_scope") == "noncommercial_internal"
        and is_noncommercial_license(event.get("license"))
        and source.startswith("local:audio/candidates/sfx/approved-noncommercial/")
        and receipt.startswith("local:audio/candidates/sfx/approved-noncommercial/")
        and receipt.endswith(".receipt.json")
        and re.fullmatch(r"[0-9a-f]{64}", str(event.get("source_sha256") or ""))
    )


# Keep this guard deliberately narrow: a character may naturally say "开门".
# Only explicit bracketed production directions are rejected here; broader
# script interpretation belongs in the authoring compiler, not the renderer.
_STAGE_DIRECTION_RE = re.compile(
    r"[（(【\[][^）)】\]]*(?:"
    r"(?:镜头|画面)(?:切换|拉近|拉远|推进|转向)|"
    r"(?:特写|远景)(?:切换|出现)|"
    r"(?:脚步声|开门声|关门声|雷声)(?:渐近|传来|响起|渐强|渐弱)|"
    r"(?:背景音(?:乐)?|音效)(?:响起|渐强|渐弱)|"
    r"字幕(?:出现|显示)"
    r")[^）)】\]]*[）)】\]]"
)


def _validate_spoken_text(text: str, field: str) -> None:
    if _STAGE_DIRECTION_RE.search(text):
        raise AudioTimelineError(
            f"{field} contains an explicit stage direction; move it to an audio or visual event"
        )


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


def compile_timeline(spec: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
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
                if event_type in VOCAL_TYPES:
                    _validate_spoken_text(text, f"{sid}.audio_cues[{cue_index}].spoken_text")
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
                            "approval_status": str(cue.get("approval_status") or ""),
                            "approval_receipt": str(cue.get("approval_receipt") or ""),
                            "production_eligible": cue.get("production_eligible"),
                            "usage_scope": str(cue.get("usage_scope") or ""),
                            "model": str(cue.get("model") or ""),
                            "checkpoint_fingerprint": str(cue.get("checkpoint_fingerprint") or ""),
                            "node_job_id": str(cue.get("node_job_id") or ""),
                            "material": str(cue.get("material") or ""),
                        }
                    )
                if event_type == "performance":
                    event.update(
                        {
                            "approval_status": str(cue.get("approval_status") or ""),
                            "approval_receipt": str(cue.get("approval_receipt") or ""),
                            "character_id": str(cue.get("character_id") or ""),
                            "language": str(cue.get("language") or ""),
                            "node_job_id": str(cue.get("node_job_id") or ""),
                            "adult_confirmed": cue.get("adult_confirmed") is True,
                            "source_authorization": str(cue.get("source_authorization") or ""),
                            "take_seed": cue.get("take_seed"),
                            "model_version": str(cue.get("model_version") or ""),
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
                _validate_spoken_text(text, f"{sid}.nar")
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
        "delivery_scope": str(spec.get("delivery_scope") or "commercial"),
        "events": events,
        "duration_sec": round(cursor, 3),
    }
    validate_timeline(timeline)
    approved_internal = [
        event for event in events if is_approved_internal_sfx(event, timeline["delivery_scope"])
    ]
    if approved_internal:
        if root is None:
            raise AudioTimelineError(
                "approved non-commercial SFX compilation requires the film root"
            )
        from sfx_candidates import approved_event_receipt_valid

        if any(not approved_event_receipt_valid(root, event) for event in approved_internal):
            raise AudioTimelineError(
                "approved non-commercial SFX receipt does not bind signed local audio"
            )
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
    delivery_scope = str(timeline.get("delivery_scope") or "commercial")
    if delivery_scope not in {"commercial", "noncommercial_internal"}:
        raise AudioTimelineError("audio-timeline.delivery_scope is invalid")
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
            _validate_spoken_text(str(event["text"]), f"{prefix}.text")
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
            license_id = str(event.get("license") or "").strip()
            if not license_id:
                raise AudioTimelineError(f"{prefix} asset license is required")
            if not str(event.get("source_sha256") or "").strip():
                raise AudioTimelineError(f"{prefix} asset source_sha256 is required")
            normalized_source = source.replace("\\", "/").lower()
            pending_candidate = (
                "/audio/candidates/" in f"/{normalized_source.removeprefix('local:')}"
                and "/pending/" in f"/{normalized_source.removeprefix('local:')}"
            )
            restricted_candidate = event_type != "performance" and (
                pending_candidate
                or is_noncommercial_license(license_id)
                or is_candidate_only_license(license_id)
                or event.get("production_eligible") is False
                or event.get("approval_status") == "pending_human_review"
            )
            if restricted_candidate and not is_approved_internal_sfx(event, delivery_scope):
                raise AudioTimelineError(
                    f"{prefix} non-commercial or pending candidate cannot enter a formal timeline"
                )
        if event_type == "performance" and not bool(event.get("muted")):
            if not str(event.get("source") or "").startswith("local:"):
                raise AudioTimelineError(f"{prefix} performance asset must be local:")
            if event.get("approval_status") != "approved":
                raise AudioTimelineError(f"{prefix} performance asset requires human approval")
            if not str(event.get("approval_receipt") or "").startswith("local:"):
                raise AudioTimelineError(
                    f"{prefix} performance asset requires local approval_receipt"
                )
            if event.get("adult_confirmed") is not True:
                raise AudioTimelineError(
                    f"{prefix} performance asset requires adult_confirmed=true"
                )
            if event.get("source_authorization") not in {"original", "authorized_reference"}:
                raise AudioTimelineError(f"{prefix} performance source authorization is invalid")
            if not str(event.get("character_id") or "").strip():
                raise AudioTimelineError(f"{prefix} performance asset requires character_id")
            if event.get("language") != "nonverbal":
                raise AudioTimelineError(f"{prefix} performance asset requires language=nonverbal")
            if not str(event.get("node_job_id") or "").strip():
                raise AudioTimelineError(f"{prefix} performance asset requires node_job_id")
            if isinstance(event.get("take_seed"), bool) or not isinstance(
                event.get("take_seed"), int
            ):
                raise AudioTimelineError(f"{prefix} performance asset requires integer take_seed")
            if not str(event.get("model_version") or "").strip():
                raise AudioTimelineError(f"{prefix} performance asset requires model_version")
            if not re.fullmatch(r"[0-9a-f]{64}", str(event.get("source_sha256") or "")):
                raise AudioTimelineError(f"{prefix} performance asset source_sha256 is invalid")
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
