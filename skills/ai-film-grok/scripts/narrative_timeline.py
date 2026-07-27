#!/usr/bin/env python3
"""Shared timeline guards used before persistence and before final rendering."""

from __future__ import annotations

import re
from typing import Any

_NARRATOR_SPEAKERS = frozenset({"storyteller", "narrator", "vo", "旁白", "os", "inner", "内心"})


class NarrativeTimelineError(ValueError):
    pass


def _speaker_key(shot: dict[str, Any]) -> str:
    return str(shot.get("speaker") or shot.get("role") or "").strip().lower()


def _is_character_speech(shot: dict[str, Any]) -> bool:
    speaker = _speaker_key(shot)
    if speaker in _NARRATOR_SPEAKERS:
        return False
    if speaker:
        return True
    return any(
        isinstance(shot.get(key), str) and shot[key].strip()
        for key in ("dialogue", "dialogue_ja", "nar_ja", "spoken_ja")
    )


def spoken_text_for_shot(
    shot: dict[str, Any],
    *,
    dialogue_spoken_lang: str = "ja",
    narration_spoken_lang: str = "zh",
    vo_mode: str = "storyteller",
) -> str:
    """Resolve exactly the text that the TTS stage will receive."""
    character = _is_character_speech(shot)
    if character and dialogue_spoken_lang.strip().lower() in {"ja", "jp", "japanese"}:
        for key in ("nar_ja", "dialogue_ja", "spoken_ja", "dialogue"):
            value = shot.get(key)
            if isinstance(value, str) and value.strip():
                text = value.strip()
                if key != "dialogue" or any("\u3040" <= char <= "\u30ff" for char in text):
                    return text
        for key in ("dialogue", "nar", "narration"):
            value = shot.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if narration_spoken_lang.strip().lower() in {"ja", "jp", "japanese"} and not character:
        for key in ("nar_ja", "nar", "narration"):
            value = shot.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("nar", "narration", "nar_zh", "dialogue", "vo", "caption"):
        value = shot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def validate_linear_narration(
    shots: list[dict[str, Any]],
    *,
    vo_mode: str,
    dialogue_spoken_lang: str = "ja",
    narration_spoken_lang: str = "zh",
) -> None:
    """Each real TTS line must advance the story rather than replay it."""
    seen: dict[str, str] = {}
    for shot in shots:
        shot_id = str(shot.get("id") or "<unknown>")
        text = spoken_text_for_shot(
            shot,
            dialogue_spoken_lang=dialogue_spoken_lang,
            narration_spoken_lang=narration_spoken_lang,
            vo_mode=vo_mode,
        )
        if not text:
            raise NarrativeTimelineError(
                f"Shot {shot_id} has no authored narration/dialogue; metadata is not playable VO"
            )
        fingerprint = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE).casefold()
        if fingerprint in seen:
            raise NarrativeTimelineError(
                f"Shot {shot_id} repeats narration from {seen[fingerprint]}; "
                "write the next causal story beat instead"
            )
        seen[fingerprint] = shot_id


def validate_sfx_scene_bindings(
    sound_plan: dict[str, Any] | None, shots: list[dict[str, Any]]
) -> None:
    """SFX must be attached to a real story shot; music and ambience may be global."""
    if not isinstance(sound_plan, dict):
        return
    shot_ids = {str(shot.get("id")) for shot in shots if isinstance(shot, dict) and shot.get("id")}
    for index, event in enumerate(sound_plan.get("events") or []):
        if not isinstance(event, dict) or event.get("type") != "sfx_accent":
            continue
        shot_id = str(event.get("shot_id") or "").strip()
        if not shot_id:
            raise NarrativeTimelineError(
                f"sound_plan.events[{index}] SFX must declare the story shot it belongs to"
            )
        if shot_id not in shot_ids:
            raise NarrativeTimelineError(
                f"sound_plan.events[{index}] SFX references unknown shot_id: {shot_id}"
            )
