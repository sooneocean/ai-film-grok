#!/usr/bin/env python3
"""Bind measured dialogue audio to on-screen delivery and post-line breathing room."""

import hashlib
import re
from pathlib import Path
from typing import Any

from performance_evidence import find_shot, performance_contract
from util import read_json, write_json

MIN_REACTION_SPACE_SEC = 0.2


def timing_recommendation(
    *, actual_duration_sec: float, usable_window_sec: float
) -> dict[str, Any]:
    """Classify a measured timing miss without mutating audio or picture."""
    actual = max(0.0, float(actual_duration_sec))
    window = max(0.0, float(usable_window_sec))
    excess = max(0.0, actual - window)
    ratio = excess / window if window else (1.0 if actual else 0.0)
    if ratio <= 0.03 + 1e-9:
        action = "accept"
    elif ratio <= 0.07 + 1e-9:
        action = "micro_stretch_review"
    elif ratio <= 0.12 + 1e-9:
        action = "regenerate_rate"
    elif ratio <= 0.20 + 1e-9:
        action = "rework_performance"
    else:
        action = "rewrite_or_extend_shot"
    return {
        "usable_window_sec": round(window, 3),
        "actual_duration_sec": round(actual, 3),
        "overrun_sec": round(excess, 3),
        "overrun_ratio": round(ratio, 4),
        "action": action,
        "automatic": False,
    }


def _hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normal(value: object) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _timeline_shots(root: Path) -> list[dict[str, Any]]:
    timeline = read_json(root / "timeline.json") or {}
    shots = timeline.get("shots") if isinstance(timeline.get("shots"), list) else []
    return [shot for shot in shots if isinstance(shot, dict) and str(shot.get("id") or "").strip()]


def build_speech_performance_timing(root: Path, *, write: bool = True) -> dict[str, Any]:
    """Create a no-spend timing receipt for lipsync dialogue shots only."""
    root = Path(root).expanduser().resolve()
    rehearsal_path = root / "receipts" / "tts-rehearsal.json"
    rehearsal = read_json(rehearsal_path) or {}
    measured = {
        str(row.get("shot_id")): row
        for row in rehearsal.get("shots") or []
        if isinstance(row, dict) and str(row.get("shot_id") or "").strip()
    }
    cursor = 0.0
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    required_count = 0
    for timeline_shot in _timeline_shots(root):
        shot_id = str(timeline_shot["id"])
        duration = max(0.0, float(timeline_shot.get("duration_sec") or 0.0))
        shot, required = find_shot(root, shot_id)
        contract = performance_contract(shot, required=required)
        voice = contract.get("channels", {}).get("voice", {})
        dialogue_required = voice.get("kind") == "dialogue" and voice.get("lipsync") is True
        row: dict[str, Any] = {
            "shot_id": shot_id,
            "start_sec": round(cursor, 3),
            "end_sec": round(cursor + duration, 3),
            "dialogue_required": dialogue_required,
        }
        if dialogue_required:
            required_count += 1
            measurement = measured.get(shot_id)
            if not measurement:
                errors.append(
                    {
                        "code": "DIALOGUE_TTS_MEASUREMENT_MISSING",
                        "shot_id": shot_id,
                        "message": "lipsync dialogue needs a measured TTS rehearsal entry",
                    }
                )
            else:
                row["tts"] = {
                    "duration_sec": measurement.get("measured_duration_sec"),
                    "text_kind": measurement.get("text_kind"),
                    "text": measurement.get("text"),
                }
                if measurement.get("text_kind") != "dialogue":
                    errors.append(
                        {
                            "code": "DIALOGUE_TTS_KIND_MISMATCH",
                            "shot_id": shot_id,
                            "message": "measured rehearsal must be explicitly marked text_kind=dialogue",
                        }
                    )
                if _normal(measurement.get("text")) != _normal(voice.get("text")):
                    errors.append(
                        {
                            "code": "DIALOGUE_TTS_TEXT_MISMATCH",
                            "shot_id": shot_id,
                            "message": "measured rehearsal text does not match the canonical dialogue",
                        }
                    )
                try:
                    audio_duration = float(measurement.get("measured_duration_sec"))
                except (TypeError, ValueError):
                    audio_duration = 0.0
                if audio_duration <= 0:
                    errors.append(
                        {
                            "code": "DIALOGUE_TTS_DURATION_INVALID",
                            "shot_id": shot_id,
                            "message": "measured dialogue duration must be positive",
                        }
                    )
                else:
                    row["timing_recommendation"] = timing_recommendation(
                        actual_duration_sec=audio_duration,
                        usable_window_sec=max(0.0, duration - MIN_REACTION_SPACE_SEC),
                    )
                review = read_json(root / "receipts" / "reviews" / f"{shot_id}.json") or {}
                evidence = (review.get("performance_contract") or {}).get("evidence") or {}
                delivery = evidence.get("dialogue_delivery") if isinstance(evidence, dict) else None
                if not isinstance(delivery, dict):
                    errors.append(
                        {
                            "code": "DIALOGUE_DELIVERY_EVIDENCE_MISSING",
                            "shot_id": shot_id,
                            "message": "approved lipsync shot needs dialogue_delivery end timestamp evidence",
                        }
                    )
                else:
                    delivery_end = float(delivery.get("timestamp_sec") or 0)
                    row["delivery_end_sec"] = delivery_end
                    if delivery_end + 0.001 < audio_duration:
                        errors.append(
                            {
                                "code": "DIALOGUE_CUTS_BEFORE_AUDIO_END",
                                "shot_id": shot_id,
                                "message": "dialogue_delivery ends before the measured spoken audio can finish",
                            }
                        )
                    if duration - delivery_end < MIN_REACTION_SPACE_SEC:
                        errors.append(
                            {
                                "code": "DIALOGUE_REACTION_SPACE_MISSING",
                                "shot_id": shot_id,
                                "message": f"keep at least {MIN_REACTION_SPACE_SEC:.1f}s after dialogue delivery before the cut",
                            }
                        )
        rows.append(row)
        cursor += duration
    report = {
        "schema_version": 1,
        "kind": "speech-performance-timing",
        "required": required_count > 0,
        "ok": not errors,
        "rehearsal": {"path": str(rehearsal_path), "sha256": _hash(rehearsal_path)},
        "shots": rows,
        "errors": errors,
        "judgment_source": "measured_audio_plus_human_observation",
        "limitation": "Audio duration is measured; dialogue_delivery is a human end-of-line observation, not automatic lip-sync recognition.",
    }
    if write:
        path = root / "receipts" / "speech-performance-timing.json"
        write_json(path, report)
        report["path"] = str(path)
        report["sha256"] = _hash(path)
    return report
