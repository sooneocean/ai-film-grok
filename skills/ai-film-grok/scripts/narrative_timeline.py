#!/usr/bin/env python3
"""Shared timeline guards used before persistence and before final rendering.

Chinese-only product path (2026-08-04): Japanese dialogue fields are ignored.
"""

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
        isinstance(shot.get(key), str)
        and shot[key].strip()
        and re.search(r"[\u4e00-\u9fff]", shot[key])
        for key in ("dialogue", "dialogue_zh", "spoken_zh", "caption_text")
    )


def spoken_text_for_shot(
    shot: dict[str, Any],
    *,
    dialogue_spoken_lang: str = "zh",
    narration_spoken_lang: str = "zh",
    vo_mode: str = "storyteller",
) -> str:
    """Resolve exactly the text that the TTS stage will receive (Chinese-only)."""
    del dialogue_spoken_lang, narration_spoken_lang, vo_mode  # policy fixed to zh
    character = _is_character_speech(shot)
    if character:
        for key in (
            "spoken_zh",
            "dialogue_zh",
            "dialogue",
            "caption_text",
            "nar",
            "spoken_text",
        ):
            value = shot.get(key)
            if isinstance(value, str) and value.strip() and re.search(r"[\u4e00-\u9fff]", value):
                return value.strip()
        for cue in shot.get("audio_cues") or []:
            if not isinstance(cue, dict) or cue.get("kind") != "voice":
                continue
            text = str(cue.get("spoken_text") or "").strip()
            if text and re.search(r"[\u4e00-\u9fff]", text):
                return text
    for key in ("nar", "narration", "nar_zh", "dialogue", "vo", "caption", "caption_text"):
        value = shot.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _is_non_vo_coverage_shot(shot: dict[str, Any]) -> bool:
    """Reaction / action_cover / silence inserts may legitimately carry no TTS line."""
    screen_mode = str(shot.get("screen_mode") or shot.get("coverage_role") or "").strip().lower()
    if screen_mode not in {"reaction", "action_cover", "silence"}:
        return False
    cues = shot.get("audio_cues") if isinstance(shot.get("audio_cues"), list) else []
    has_voice = any(
        isinstance(cue, dict) and str(cue.get("kind") or "").strip().lower() == "voice"
        for cue in cues
    )
    has_authored_speech = any(
        isinstance(shot.get(key), str) and shot[key].strip()
        for key in (
            "nar",
            "narration",
            "nar_zh",
            "dialogue",
            "dialogue_zh",
            "spoken_zh",
            "vo",
            "caption",
            "caption_text",
        )
    )
    return not has_voice and not has_authored_speech


def validate_linear_narration(
    shots: list[dict[str, Any]],
    *,
    vo_mode: str,
    dialogue_spoken_lang: str = "zh",
    narration_spoken_lang: str = "zh",
) -> None:
    """Each real TTS line must advance the story rather than replay it."""
    seen: dict[str, str] = {}
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        shot_id = str(shot.get("id") or "<unknown>")
        if _is_non_vo_coverage_shot(shot):
            continue
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
