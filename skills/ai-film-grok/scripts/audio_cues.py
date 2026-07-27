"""Shot-local audio cue contract and deterministic timeline compiler.

Voice text and non-voice sound are deliberately separate: only ``voice`` cues
carry ``spoken_text`` and are eligible for TTS.
"""

from __future__ import annotations

from typing import Any
import re


class AudioCueError(ValueError):
    pass


VOICE_TYPES = frozenset({"dialogue", "inner_monologue", "phone_broadcast", "narration"})
NON_VOICE_KINDS = frozenset({"foley", "sfx", "ambience", "music", "silence"})
ALL_KINDS = frozenset({"voice", *NON_VOICE_KINDS})
_STAGE_DIRECTION = re.compile(r"(?:^|\s)[\[\(（](?:sfx|foley|ambience|sound|脚步|开门|关门|雨声|风声|环境音)", re.I)


def _number(value: object, *, field: str, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AudioCueError(f"{field} must be a number")
    value = float(value)
    if value < minimum:
        raise AudioCueError(f"{field} must be >= {minimum}")
    return value


def validate_audio_cues(shots: list[dict[str, Any]], *, strict: bool) -> dict[str, Any]:
    """Validate shot-local audio without forcing legacy films to migrate.

    ``strict`` turns malformed authored cues into a hard error.  In either
    mode, a cue cannot accidentally expose non-voice text to the TTS path.
    """
    warnings: list[str] = []
    voice_count = 0
    for shot in shots:
        sid = str(shot.get("id") or "<unknown>")
        raw = shot.get("audio_cues")
        if raw is None:
            if strict:
                warnings.append(f"{sid}: audio_cues missing")
            continue
        if not isinstance(raw, list):
            raise AudioCueError(f"{sid}.audio_cues must be an array")
        if strict and not raw:
            raise AudioCueError(f"{sid}.audio_cues cannot be empty in strict mode")
        duration = _number(shot.get("duration_sec", 0), field=f"{sid}.duration_sec")
        for index, cue in enumerate(raw):
            prefix = f"{sid}.audio_cues[{index}]"
            if not isinstance(cue, dict):
                raise AudioCueError(f"{prefix} must be an object")
            kind = str(cue.get("kind") or "").strip().lower()
            if kind not in ALL_KINDS:
                raise AudioCueError(f"{prefix}.kind must be one of {sorted(ALL_KINDS)}")
            start = _number(cue.get("start_offset_sec", 0), field=f"{prefix}.start_offset_sec")
            cue_duration = _number(cue.get("duration_sec", 0), field=f"{prefix}.duration_sec")
            if start + cue_duration > duration + 1e-6:
                raise AudioCueError(f"{prefix} exceeds {sid}.duration_sec")
            spoken = cue.get("spoken_text")
            if kind == "voice":
                voice_count += 1
                if not isinstance(spoken, str) or not spoken.strip():
                    raise AudioCueError(f"{prefix}.spoken_text is required for voice")
                if _STAGE_DIRECTION.search(spoken):
                    raise AudioCueError(f"{prefix}.spoken_text contains a sound/action direction")
                if not str(cue.get("speaker") or "").strip():
                    raise AudioCueError(f"{prefix}.speaker is required for voice")
                line_type = str(cue.get("line_type") or "").strip().lower()
                if line_type not in VOICE_TYPES:
                    raise AudioCueError(
                        f"{prefix}.line_type must be one of {sorted(VOICE_TYPES)}"
                    )
                if cue.get("asset_hint") is not None or cue.get("action_hint") is not None:
                    raise AudioCueError(f"{prefix} voice cannot carry action or asset hints")
            elif spoken is not None:
                raise AudioCueError(f"{prefix}.spoken_text is only allowed on voice cues")
            elif kind != "silence" and not str(cue.get("asset_hint") or "").strip():
                raise AudioCueError(f"{prefix}.asset_hint is required for non-voice sound")
    if strict and warnings:
        raise AudioCueError("audio_cues_strict: " + "; ".join(warnings))
    return {"strict": strict, "warnings": warnings, "voice_cues": voice_count}


def strict_tts_text(shot: dict[str, Any], *, strict: bool) -> str | None:
    """Resolve TTS text without allowing legacy action fields in strict mode."""
    cue = primary_voice_cue(shot)
    if cue is not None:
        return str(cue["spoken_text"]).strip()
    if strict:
        raise AudioCueError(f"{shot.get('id')}: strict audio cues require a voice cue for TTS")
    return None


def primary_voice_cue(shot: dict[str, Any]) -> dict[str, Any] | None:
    """Return the executable voice cue; multiple dialogue turns need a split shot."""
    cues = shot.get("audio_cues")
    if not isinstance(cues, list):
        return None
    voices = [cue for cue in cues if isinstance(cue, dict) and cue.get("kind") == "voice"]
    if len(voices) > 1:
        raise AudioCueError(f"{shot.get('id')}: split multiple voice cues into separate shots")
    return voices[0] if voices else None


def compile_audio_timeline(
    shots: list[dict[str, Any]], *, shot_starts: dict[str, float]
) -> list[dict[str, Any]]:
    """Expand relative shot cues to auditable absolute-film timeline rows."""
    rows: list[dict[str, Any]] = []
    for shot in shots:
        sid = str(shot.get("id") or "")
        base = float(shot_starts.get(sid, 0.0))
        for index, cue in enumerate(shot.get("audio_cues") or []):
            if not isinstance(cue, dict):
                continue
            start = base + float(cue.get("start_offset_sec") or 0.0)
            duration = float(cue.get("duration_sec") or 0.0)
            row = {
                "shot_id": sid,
                "cue_index": index,
                "kind": cue.get("kind"),
                "start_sec": round(start, 3),
                "end_sec": round(start + duration, 3),
            }
            for key in ("speaker", "line_type", "spoken_text", "emotion", "performance", "asset_hint", "purpose"):
                if cue.get(key) is not None:
                    row[key] = cue[key]
            rows.append(row)
    return rows
