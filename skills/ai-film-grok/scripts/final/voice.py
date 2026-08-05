"""Voice role / language lock helpers (peeled from render_final · W4)."""

from __future__ import annotations

import re

from typing import Any

from final.caption_text import (
    _shot_speaker_key,
    is_character_speech_shot,
    spoken_text_for_shot,
)
from final.errors import RenderError

# Voice / caption defaults (peeled from render_final W4)
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"  # edge 显式后端默认女声
STORYTELLER_VOICE = "zh-CN-XiaoxiaoNeural"
# P0 · 2026-08-04: Chinese-only character dialogue (Japanese retired)
HEROINE_ZH_VOICE = "zh-CN-XiaoyiNeural"
PARTNER_ZH_VOICE = "zh-CN-YunxiNeural"
_NARRATOR_SPEAKERS = frozenset({"storyteller", "narrator", "vo", "旁白", "os", "inner", "内心"})
_HEROINE_SPEAKERS = frozenset(
    {"heroine", "female", "fufu", "girl", "woman", "she", "女主", "沈筱", "astra"}
)
_PARTNER_SPEAKERS = frozenset(
    {"partner", "male_hero", "hero", "male", "boy", "man", "he", "男主", "杨舟"}
)


def _locked_voice_role(shot: dict[str, Any]) -> str | None:
    """Return the immutable cast role for the three production voice tracks."""
    speaker = _shot_speaker_key(shot)
    if speaker in _NARRATOR_SPEAKERS:
        return "storyteller"
    if speaker in _HEROINE_SPEAKERS:
        return "heroine"
    if speaker in _PARTNER_SPEAKERS:
        return "partner"
    return None

def validate_voice_language_locks(
    shots: list[dict[str, Any]], *, dialogue_spoken_lang: str
) -> None:
    """Fail closed if a named lead loses its Chinese-locked spoken track.

    Product policy 2026-08-04: Chinese-only. Japanese is retired.
    """
    dlang = (dialogue_spoken_lang or "zh").strip().lower()
    if dlang in {"ja", "jp", "japanese"}:
        raise RenderError(
            "Japanese dialogue is retired; set dialogue_spoken_lang=zh and Chinese spoken text"
        )
    for shot in shots:
        role = _locked_voice_role(shot)
        if role is None:
            continue
        sid = str(shot.get("id") or "<unknown>")
        explicit = shot.get("vo_voice") or shot.get("voice")
        if isinstance(explicit, str) and explicit.strip():
            raise RenderError(
                f"Shot {sid} ({role}) must use its cast_voices lock, not per-shot vo_voice"
            )
        explicit_backend = shot.get("tts_backend")
        if isinstance(explicit_backend, str) and explicit_backend.strip():
            raise RenderError(
                f"Shot {sid} ({role}) must use its cast_tts_backends lock, not per-shot tts_backend"
            )
        if role == "storyteller":
            continue
        chinese_line = next(
            (
                str(shot[key]).strip()
                for key in (
                    "dialogue",
                    "spoken_zh",
                    "dialogue_zh",
                    "caption_text",
                    "nar",
                    "spoken_text",
                )
                if isinstance(shot.get(key), str) and shot[key].strip()
            ),
            "",
        )
        if not chinese_line:
            for cue in shot.get("audio_cues") or []:
                if (
                    isinstance(cue, dict)
                    and cue.get("kind") == "voice"
                    and str(cue.get("spoken_text") or "").strip()
                ):
                    chinese_line = str(cue.get("spoken_text")).strip()
                    break
        if not chinese_line or not re.search(r"[\u4e00-\u9fff]", chinese_line):
            raise RenderError(
                f"Shot {sid} ({role}) needs Chinese spoken/caption text; "
                "dialogue_spoken_lang=zh only (Japanese retired)"
            )

def tts_backend_for_shot(
    shot: dict[str, Any], *, default_backend: str, cast_tts_backends: dict[str, str] | None
) -> str:
    """Resolve a locked TTS provider per named role, without shot-level switching."""
    locked_role = _locked_voice_role(shot)
    if locked_role is None:
        explicit = shot.get("tts_backend")
        return (
            str(explicit).strip()
            if isinstance(explicit, str) and explicit.strip()
            else default_backend
        )
    providers = cast_tts_backends or {}
    provider = providers.get(locked_role, default_backend)
    if not isinstance(provider, str) or not provider.strip():
        raise RenderError(f"{locked_role} TTS backend lock must be a non-empty string")
    provider = provider.strip().lower()
    if provider == "auto" and locked_role in providers:
        raise RenderError(
            f"{locked_role} cast_tts_backends must name an explicit provider, not auto"
        )
    if provider == "auto":
        # Existing films that did not yet author a per-role provider retain the
        # safe, deterministic Edge default instead of silently probing another TTS.
        return "edge"
    return provider

def voice_for_shot(
    shot: dict[str, Any],
    *,
    default_voice: str,
    cast_voices: dict[str, str] | None,
    vo_mode: str,
    dialogue_spoken_lang: str = "zh",
) -> str:
    """Resolve one stable voice id for this shot — 一角一声 (Chinese-only)."""
    cast_voices = cast_voices or {}
    heroine_default = cast_voices.get("heroine") or HEROINE_ZH_VOICE
    partner_default = (
        cast_voices.get("partner")
        or cast_voices.get("male_hero")
        or cast_voices.get("hero")
        or PARTNER_ZH_VOICE
    )
    locked_role = _locked_voice_role(shot)
    if locked_role == "storyteller":
        return cast_voices.get("storyteller") or STORYTELLER_VOICE
    if locked_role == "heroine":
        return heroine_default
    if locked_role == "partner":
        return partner_default
    explicit = shot.get("vo_voice") or shot.get("voice")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    speaker = shot.get("speaker") or shot.get("role")
    if isinstance(speaker, str) and speaker.strip() and speaker.strip() in cast_voices:
        return cast_voices[speaker.strip()]
    # map first cast tag if present (character mode)
    casts = (
        shot.get("dsl", {}).get("cast") if isinstance(shot.get("dsl"), dict) else shot.get("cast")
    )
    if isinstance(casts, list) and casts:
        c0 = str(casts[0]).strip()
        if c0 in cast_voices:
            return cast_voices[c0]
    sp = _shot_speaker_key(shot)
    if is_character_speech_shot(shot):
        if sp in cast_voices:
            return cast_voices[sp]
        if sp in _PARTNER_SPEAKERS or any(k in cast_voices for k in ("partner", "male_hero")):
            for k in ("partner", "male_hero", "hero"):
                if k in cast_voices:
                    return cast_voices[k]
            if sp in _PARTNER_SPEAKERS:
                return partner_default
        if sp in _HEROINE_SPEAKERS or "heroine" in cast_voices:
            if "heroine" in cast_voices:
                return cast_voices["heroine"]
            return heroine_default
        return cast_voices.get("heroine") or heroine_default
    if vo_mode == "storyteller" and "storyteller" in cast_voices:
        return cast_voices["storyteller"]
    if "storyteller" in cast_voices and not is_character_speech_shot(shot):
        return cast_voices["storyteller"]
    return default_voice

