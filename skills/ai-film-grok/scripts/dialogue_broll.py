#!/usr/bin/env python3
"""Validated editorial coverage for dialogue-led films.

B-roll lives beneath its speaking A-roll: it replaces picture for a bounded
interval while the parent dialogue, captions, and audio clock continue.
"""

from __future__ import annotations

import math
from typing import Any


class DialogueBrollError(ValueError):
    pass


MIN_DIALOGUE_SEC = 6.0
EDGE_HANDLE_SEC = 0.8
MAX_DIALOGUE_COVERAGE_RATIO = 0.40
MIN_A_ROLL_RATIO = 0.60


def iter_dialogue_broll(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Return B-roll entries in film order, annotated with their parent shot."""
    found: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            for entry in shot.get("dialogue_broll") or []:
                if isinstance(entry, dict):
                    found.append({**entry, "parent_shot_id": shot.get("id")})
    return found


def default_dialogue_broll(shot: dict[str, Any]) -> list[dict[str, Any]]:
    """Produce one conservative, no-face insert for a sufficiently long line."""
    duration = float(shot.get("duration_sec") or 0.0)
    if duration < MIN_DIALOGUE_SEC:
        return []
    available = duration - 2 * EDGE_HANDLE_SEC
    cover_duration = min(2.5, max(1.5, round(duration * 0.28, 2)), available, duration * 0.40)
    if cover_duration < 1.5:
        return []
    start = round((duration - cover_duration) / 2, 2)
    parent_id = str(shot.get("id") or "shot")
    source_dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return [
        {
            "id": f"{parent_id}__broll01",
            "kind": "insert",
            "parent_shot_id": parent_id,
            "start_sec": start,
            "end_sec": round(start + cover_duration, 2),
            "cut_trigger": "dialogue_turn",
            "narrative_purpose": "show the concrete object or environmental consequence named by the dialogue",
            "audio_policy": "carry_parent_dialogue",
            "shot_role": "insert",
            "speaker_on_camera": False,
            "lipsync": False,
            "dsl": {
                "subject": "story-relevant object or environmental detail, no people, no face",
                "action": "a small observable change that answers the dialogue beat",
                "motion": "restrained detail movement; frame stays empty",
                "camera": {"shot_size": "close-up"},
                "location_id": source_dsl.get("location_id") or shot.get("location_id"),
            },
        }
    ]


def validate_dialogue_broll(shot: dict[str, Any], *, shot_id: str) -> list[dict[str, Any]]:
    entries = shot.get("dialogue_broll")
    if entries is None:
        return []
    if str(shot.get("screen_mode") or "").strip().lower() != "on_camera":
        raise DialogueBrollError(
            f"{shot_id}.dialogue_broll is only allowed on an on_camera dialogue A-roll"
        )
    if not isinstance(entries, list) or len(entries) > 1:
        raise DialogueBrollError(f"{shot_id}.dialogue_broll must contain at most one entry")
    duration = float(shot.get("duration_sec") or 0.0)
    validated: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise DialogueBrollError(f"{shot_id}.dialogue_broll entry must be an object")
        bid = str(entry.get("id") or "").strip()
        if not bid or not bid.startswith(f"{shot_id}__broll"):
            raise DialogueBrollError(
                f"{shot_id}.dialogue_broll id must start with {shot_id}__broll"
            )
        if str(entry.get("parent_shot_id") or shot_id) != shot_id:
            raise DialogueBrollError(f"{bid}.parent_shot_id must equal {shot_id}")
        kind = str(entry.get("kind") or "").lower()
        if kind not in {"env", "insert", "reaction"}:
            raise DialogueBrollError(f"{bid}.kind must be env, insert, or reaction")
        try:
            start, end = float(entry["start_sec"]), float(entry["end_sec"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DialogueBrollError(f"{bid} requires numeric start_sec/end_sec") from exc
        if not all(math.isfinite(value) for value in (duration, start, end)):
            raise DialogueBrollError(f"{bid} start_sec/end_sec and parent duration must be finite")
        if start < EDGE_HANDLE_SEC or end > duration - EDGE_HANDLE_SEC or end <= start:
            raise DialogueBrollError(f"{bid} must stay inside the parent 0.8s edge handles")
        if end - start > duration * MAX_DIALOGUE_COVERAGE_RATIO + 1e-6:
            raise DialogueBrollError(f"{bid} exceeds the 40% dialogue coverage limit")
        if entry.get("speaker_on_camera") is not False or entry.get("lipsync") is not False:
            raise DialogueBrollError(f"{bid} must set speaker_on_camera=false and lipsync=false")
        if entry.get("audio_policy") != "carry_parent_dialogue":
            raise DialogueBrollError(f"{bid}.audio_policy must be carry_parent_dialogue")
        dsl = entry.get("dsl")
        if not isinstance(dsl, dict) or not str(dsl.get("motion") or "").strip():
            raise DialogueBrollError(f"{bid} requires a visual dsl with motion")
        if kind in {"env", "insert"}:
            blob = " ".join(str(dsl.get(k) or "") for k in ("subject", "action", "motion", "cast"))
            positive_blob = blob.lower().replace("no face", "").replace("no people", "")
            if dsl.get("cast") or any(
                word in positive_blob for word in ("face", "portrait", "person", "character")
            ):
                raise DialogueBrollError(f"{bid} {kind} B-roll must be no-face and carry no cast")
            if str(entry.get("shot_role") or "") not in {"env", "insert"}:
                raise DialogueBrollError(f"{bid} {kind} B-roll must use matching no-face shot_role")
        else:
            cast = dsl.get("cast")
            if not isinstance(cast, list) or len(cast) != 1 or not str(cast[0]).strip():
                raise DialogueBrollError(
                    f"{bid} reaction B-roll requires exactly one locked listener cast"
                )
            if entry.get("shot_role") != "hero":
                raise DialogueBrollError(f"{bid} reaction B-roll must use shot_role=hero")
        validated.append(entry)
    return validated
