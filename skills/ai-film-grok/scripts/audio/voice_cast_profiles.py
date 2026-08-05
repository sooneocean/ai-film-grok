#!/usr/bin/env python3
"""Stable, language-locked voice-cast profile helpers.

Product policy 2026-08-04: Chinese-only dialogue / narration. Japanese is retired.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

ZH_POOL = ("zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural", "zh-CN-YunxiNeural", "zh-CN-YunjianNeural")
NARRATOR_SPEAKERS = frozenset(
    {"narrator", "storyteller", "broadcast", "announcer", "radio", "system"}
)
VOCAL_LANGUAGE = {"dialogue": "zh", "inner_voice": "zh", "media_voice": "zh", "narration": "zh"}


class VoiceCastError(ValueError):
    pass


def _normalize_lang(raw: str) -> str:
    lang = (raw or "").strip().lower()
    if lang in {"", "zh", "cn", "chinese", "zh-cn", "zh_cn"}:
        return "zh"
    if lang in {"ja", "jp", "japanese"}:
        raise VoiceCastError(
            "Japanese dialogue is retired; use Chinese spoken_text (dialogue_spoken_lang=zh only)"
        )
    raise VoiceCastError(f"unsupported language {raw!r}; only zh is allowed")


def event_language(event: dict[str, Any]) -> str:
    """Resolve language — Chinese-only product path."""
    explicit = (
        str(
            event.get("language")
            or event.get("spoken_lang")
            or event.get("dialogue_spoken_lang")
            or ""
        )
        .strip()
        .lower()
    )
    if explicit:
        return _normalize_lang(explicit)
    event_type = str(event.get("type") or "").strip().lower()
    speaker = str(event.get("speaker") or event.get("speaker_id") or "").strip().lower()
    if event_type == "narration" or speaker in NARRATOR_SPEAKERS:
        return "zh"
    return VOCAL_LANGUAGE.get(event_type, "zh")


def profile_hash(profile: dict[str, Any]) -> str:
    clean = {
        key: value for key, value in profile.items() if key not in {"profile_hash", "tts_stale"}
    }
    return hashlib.sha256(
        json.dumps(clean, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def assign_profiles(
    speakers: list[dict[str, Any]], existing: dict[str, Any] | None = None
) -> dict[str, Any]:
    existing = existing or {}
    profiles: dict[str, Any] = {}
    used: set[str] = set()
    for item in speakers:
        speaker_id = str(item.get("speaker_id") or item.get("id") or "").strip()
        if not speaker_id:
            raise VoiceCastError("speaker_id is required")
        old = existing.get(speaker_id) if isinstance(existing.get(speaker_id), dict) else {}
        requested_language = str(item.get("language") or "").lower()
        old_language = str(old.get("language") or "").lower()
        if requested_language:
            requested_language = _normalize_lang(requested_language)
        if old_language in {"ja", "jp", "japanese"}:
            # Migrate legacy locked JA profiles to zh on next cast (must re-lock voice).
            old_language = ""
        if (
            bool(old.get("locked"))
            and requested_language
            and old_language
            and requested_language != old_language
            and old_language != "zh"
        ):
            raise VoiceCastError(
                f"{speaker_id} is locked to {old_language}; create a new voice profile before changing language"
            )
        language = requested_language or (old_language if old_language == "zh" else "") or "zh"
        language = _normalize_lang(language)
        pool = ZH_POOL
        locked = bool(old.get("locked", item.get("locked", False)))
        # Drop legacy ja-JP voice ids even if locked — force Chinese pool.
        voice = ""
        if locked:
            voice = str(old.get("voice_id") or item.get("voice_id") or "").strip()
        if not voice:
            voice = str(item.get("voice_id") or old.get("voice_id") or "").strip()
        if voice.startswith("ja-JP-") or voice.startswith("ja-"):
            voice = ""
        if not voice:
            offset = int(hashlib.sha256(speaker_id.encode("utf-8")).hexdigest(), 16) % len(pool)
            voice = next(
                (
                    pool[(offset + step) % len(pool)]
                    for step in range(len(pool))
                    if pool[(offset + step) % len(pool)] not in used
                ),
                pool[offset],
            )
        provider = str(item.get("provider") or old.get("provider") or "edge").strip().lower()
        profile = {
            "speaker_id": speaker_id,
            "language": language,
            "provider": provider,
            "voice_id": voice,
            "tags": list(item.get("tags") or old.get("tags") or []),
            "rate": str(item.get("rate") or old.get("rate") or "+0%"),
            "pitch": str(item.get("pitch") or old.get("pitch") or "+0Hz"),
            "pan": float(item.get("pan", old.get("pan", 0.0))),
            "sample_asset": item.get("sample_asset") or old.get("sample_asset"),
            "locked": locked,
        }
        profile["profile_hash"] = profile_hash(profile)
        profile["tts_stale"] = bool(
            old and old.get("profile_hash") not in {None, profile["profile_hash"]}
        )
        profiles[speaker_id] = profile
        used.add(voice)
    return profiles


def validate_event_language(event: dict[str, Any], profile: dict[str, Any]) -> None:
    expected = event_language(event)
    if expected and profile.get("language") != expected:
        raise VoiceCastError(
            f"{event.get('id')} requires {expected} voice but {profile.get('speaker_id')} is {profile.get('language')}"
        )
