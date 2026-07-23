#!/usr/bin/env python3
"""Pure validation for locked voice and key-dialogue audio contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_VOICE_FIELDS = {
    "provider",
    "voice_id",
    "rate",
    "emphasis",
    "pauses_ms",
    "emotion_range",
}


def _issue(code: str, message: str, **context: str) -> dict[str, str]:
    return {"code": code, "message": message, **context}


def _data(bible: Mapping[str, Any], node: str) -> Mapping[str, Any]:
    nodes = bible.get("nodes")
    value = nodes.get(node) if isinstance(nodes, Mapping) else None
    data = value.get("data") if isinstance(value, Mapping) else None
    return data if isinstance(data, Mapping) else {}


def _characters(bible: Mapping[str, Any]) -> Mapping[str, Any]:
    value = _data(bible, "voice").get("characters")
    return value if isinstance(value, Mapping) else {}


def _provider_changes(
    current: Mapping[str, Any], previous: Mapping[str, Any]
) -> list[tuple[str, str, str]]:
    changes: list[tuple[str, str, str]] = []
    old_characters = _characters(previous)
    for character_id, voice in _characters(current).items():
        old_voice = old_characters.get(character_id)
        if not isinstance(voice, Mapping) or not isinstance(old_voice, Mapping):
            continue
        old_provider = str(old_voice.get("provider") or "")
        new_provider = str(voice.get("provider") or "")
        if old_provider and new_provider and old_provider != new_provider:
            changes.append((str(character_id), old_provider, new_provider))
    return changes


def _change_acknowledged(bible: Mapping[str, Any], character_id: str, old: str, new: str) -> bool:
    raw = bible.get("provider_change")
    changes = raw if isinstance(raw, list) else [raw]
    return any(
        isinstance(item, Mapping)
        and str(item.get("character_id") or character_id) == character_id
        and item.get("from") == old
        and item.get("to") == new
        and bool(str(item.get("reason") or "").strip())
        and item.get("approved_by") in {"human", "user"}
        for item in changes
    )


def _validate_bgm(bible: Mapping[str, Any], errors: list[dict[str, str]]) -> None:
    data = _data(bible, "bgm_motif_cue")
    license_data = data.get("license")
    if not str(data.get("motif") or "").strip():
        errors.append(_issue("BGM_MOTIF_MISSING", "BGM needs a named dramatic motif"))
    if not (
        isinstance(license_data, Mapping)
        and str(license_data.get("source") or "").strip()
        and str(license_data.get("license_id") or "").strip()
    ):
        errors.append(_issue("BGM_LICENSE_MISSING", "BGM needs source and license provenance"))
    cues = data.get("cues")
    if not isinstance(cues, list) or not cues:
        errors.append(_issue("BGM_CUES_MISSING", "BGM needs explicit cue in/out"))
        return
    for index, cue in enumerate(cues):
        cue_id = str(cue.get("cue_id") or index) if isinstance(cue, Mapping) else str(index)
        try:
            valid = (
                isinstance(cue, Mapping)
                and float(cue["in_sec"]) >= 0
                and float(cue["out_sec"]) > float(cue["in_sec"])
                and float(cue["silence_before_sec"]) >= 0
                and float(cue["silence_after_sec"]) >= 0
                and float(cue["ducking_db"]) <= 0
            )
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            errors.append(
                _issue(
                    "BGM_CUE_INVALID",
                    "BGM cue needs in/out, silence handles, and non-positive ducking",
                    cue_id=cue_id,
                )
            )


def validate_audio_bible(
    bible: Mapping[str, Any], *, previous: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Validate authored locks without mutating or promoting bible state."""
    errors: list[dict[str, str]] = []
    characters = _characters(bible)
    if not characters:
        errors.append(_issue("VOICE_LOCK_MISSING", "audio bible has no character voice locks"))
    for character_id, voice in characters.items():
        if not isinstance(voice, Mapping):
            missing = sorted(_VOICE_FIELDS)
        else:
            missing = sorted(
                field
                for field in _VOICE_FIELDS
                if field not in voice
                or voice.get(field) is None
                or voice.get(field) == ""
                or voice.get(field) == []
            )
        if missing:
            errors.append(
                _issue(
                    "VOICE_LOCK_INCOMPLETE",
                    f"voice lock is missing: {', '.join(missing)}",
                    character_id=str(character_id),
                )
            )

    dialogue = _data(bible, "dialogue_delivery").get("key_dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        errors.append(_issue("KEY_DIALOGUE_LOCK_MISSING", "audio bible has no key-dialogue locks"))
    else:
        for index, line in enumerate(dialogue):
            line_id = str(line.get("line_id") or index) if isinstance(line, Mapping) else str(index)
            valid = (
                isinstance(line, Mapping)
                and bool(str(line.get("line_id") or "").strip())
                and bool(str(line.get("character_id") or "").strip())
                and bool(_SHA256.fullmatch(str(line.get("text_sha256") or "")))
                and bool(str(line.get("delivery") or "").strip())
                and isinstance(line.get("lipsync_required"), bool)
            )
            if not valid:
                errors.append(
                    _issue(
                        "KEY_DIALOGUE_LOCK_INCOMPLETE",
                        "key dialogue requires line/character ids, text checksum, delivery, and lipsync requirement",
                        line_id=line_id,
                    )
                )

    _validate_bgm(bible, errors)
    if previous is not None:
        for character_id, old, new in _provider_changes(bible, previous):
            if not _change_acknowledged(bible, character_id, old, new):
                errors.append(
                    _issue(
                        "VOICE_PROVIDER_CHANGED_UNACKNOWLEDGED",
                        "voice provider changed without an exact human-approved change record",
                        character_id=character_id,
                    )
                )
    return {
        "ok": not errors,
        "kind": "audio-bible-validation",
        "errors": errors,
        "advisory_only": True,
    }
