#!/usr/bin/env python3
"""Pure validation for dialogue timing, origin, delivery, and lipsync truth."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_TRUE_LIPSYNC_METHODS = {
    "generated_native_audio",
    "recorded_performance",
    "phoneme_aligned_resync",
    "face_animation_to_audio",
}


def _issue(code: str, message: str, line_id: str = "") -> dict[str, str]:
    return {"code": code, "message": message, "line_id": line_id}


def _window(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        start = float(value["start_sec"])
        end = float(value["end_sec"])
    except (KeyError, TypeError, ValueError):
        return None
    return (start, end) if 0 <= start < end else None


def validate_dialogue_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    """Validate claims; never upgrades post VO into native or human-approved lipsync."""
    errors: list[dict[str, str]] = []
    shot_window = _window(contract.get("shot_window"))
    if shot_window is None:
        errors.append(_issue("SHOT_WINDOW_INVALID", "dialogue contract needs a valid shot window"))
    lines = contract.get("lines")
    if not isinstance(lines, list) or not lines:
        errors.append(_issue("DIALOGUE_LINES_MISSING", "dialogue contract has no lines"))
        lines = []
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if not isinstance(line, Mapping):
            errors.append(_issue("DIALOGUE_LINE_INVALID", "dialogue line must be an object"))
            continue
        line_id = str(line.get("line_id") or index)
        window = _window(line.get("window"))
        if (
            not _SHA256.fullmatch(str(line.get("text_sha256") or ""))
            or not str(line.get("delivery") or "").strip()
            or not isinstance(line.get("lipsync_required"), bool)
        ):
            errors.append(
                _issue(
                    "DIALOGUE_LINE_INCOMPLETE",
                    "dialogue needs text checksum, delivery, and explicit lipsync requirement",
                    line_id,
                )
            )
        if window is None:
            errors.append(_issue("DIALOGUE_WINDOW_INVALID", "dialogue window is invalid", line_id))
        elif shot_window and (window[0] < shot_window[0] or window[1] > shot_window[1]):
            errors.append(
                _issue(
                    "DIALOGUE_OUTSIDE_SHOT_WINDOW",
                    "dialogue window must be contained by its shot window",
                    line_id,
                )
            )

        origin = str(line.get("audio_origin") or "")
        source_silent = line.get("source_video_audio") == "silent"
        if origin == "post_vo" and source_silent:
            errors.append(
                _issue(
                    "POST_VO_NOT_NATIVE_AUDIO",
                    "post-added VO on silent I2V is not native production audio",
                    line_id,
                )
            )
        evidence = line.get("lipsync_evidence")
        method = str(evidence.get("method") or "") if isinstance(evidence, Mapping) else ""
        artifact_hash = (
            str(evidence.get("artifact_sha256") or "") if isinstance(evidence, Mapping) else ""
        )
        true_lipsync = method in _TRUE_LIPSYNC_METHODS and bool(_SHA256.fullmatch(artifact_hash))
        if line.get("lipsync_required") is True and not true_lipsync:
            errors.append(
                _issue(
                    "TRUE_LIPSYNC_EVIDENCE_MISSING",
                    "required lipsync needs a hash-bound native/performance or phoneme-aligned method",
                    line_id,
                )
            )
        rows.append(
            {
                "line_id": line_id,
                "audio_origin": origin,
                "native_audio": origin == "native" and not source_silent,
                "true_lipsync": true_lipsync,
            }
        )
    return {
        "ok": not errors,
        "kind": "dialogue-contract-validation",
        "shot_id": contract.get("shot_id"),
        "lines": rows,
        "errors": errors,
        "advisory_only": True,
    }
