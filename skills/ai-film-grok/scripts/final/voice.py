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


def check_vo_window_triangle(
    tts_dur: float,
    cue_offset: float,
    cue_window: float,
    slot: float,
    *,
    slack_sec: float = 0.03,
) -> tuple[bool, str]:
    """口白窗三角 (suse EP01 IRON): tts ≤ cue ≤ remaining slot after offset.

    Returns (ok, code). Codes: ok | cue_exceeds_slot | tts_exceeds_cue | bad_slot
    """
    try:
        tts = float(tts_dur)
        off = float(cue_offset)
        win = float(cue_window)
        plate = float(slot)
    except (TypeError, ValueError):
        return False, "bad_slot"
    if plate <= 0:
        return False, "bad_slot"
    if off < 0 or win < 0 or tts < 0:
        return False, "bad_slot"
    if off + win > plate + 1e-6:
        return False, "cue_exceeds_slot"
    if win > 0 and tts > win + float(slack_sec):
        return False, "tts_exceeds_cue"
    return True, "ok"

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

def normalize_cast_voices(cast_voices_raw: Any) -> dict[str, str]:
    """Normalize film-spec ``cast_voices`` into a Chinese-locked dict.

    Pure leaf peeled from render_final(): drops non-string / empty entries,
    fills the Chinese-only role defaults (Japanese retired 2026-08-04), and
    remaps legacy ``ja-JP-*`` / ``ja-*`` voice ids back to Chinese locks so
    Chinese TTS never inherits a Japanese voice.
    """
    cast_voices: dict[str, str] = {}
    if isinstance(cast_voices_raw, dict):
        for k, v in cast_voices_raw.items():
            if isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip():
                cast_voices[k.strip()] = v.strip()
    # Chinese-only cast defaults (Japanese retired 2026-08-04)
    cast_voices.setdefault("heroine", HEROINE_ZH_VOICE)
    cast_voices.setdefault("partner", PARTNER_ZH_VOICE)
    cast_voices.setdefault("male_hero", PARTNER_ZH_VOICE)
    cast_voices.setdefault("storyteller", STORYTELLER_VOICE)
    # Strip legacy ja-JP locks so Chinese TTS never inherits Japanese voice ids.
    for _role, _vid in list(cast_voices.items()):
        if isinstance(_vid, str) and (_vid.startswith("ja-JP-") or _vid.startswith("ja-")):
            if _role in {"heroine"}:
                cast_voices[_role] = HEROINE_ZH_VOICE
            elif _role in {"partner", "male_hero", "hero"}:
                cast_voices[_role] = PARTNER_ZH_VOICE
            else:
                cast_voices[_role] = STORYTELLER_VOICE
    return cast_voices


def normalize_cast_tts_backends(cast_tts_backends_raw: Any) -> dict[str, str]:
    """Normalize film-spec ``cast_tts_backends`` into role → lowercased provider.

    Pure leaf peeled from render_final(): raises ``RenderError`` when the
    configured value is not an object, strips whitespace and lowercases each
    provider, and drops empty / non-string entries.
    """
    if not isinstance(cast_tts_backends_raw, dict):
        raise RenderError("cast_tts_backends must be an object when configured")
    cast_tts_backends: dict[str, str] = {}
    for role, provider in cast_tts_backends_raw.items():
        if (
            isinstance(role, str)
            and isinstance(provider, str)
            and role.strip()
            and provider.strip()
        ):
            cast_tts_backends[role.strip()] = provider.strip().lower()
    return cast_tts_backends


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

