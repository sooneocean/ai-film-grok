#!/usr/bin/env python3
"""Stable, language-locked voice-cast profile helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

ZH_POOL = ("zh-CN-XiaoxiaoNeural", "zh-CN-XiaoyiNeural", "zh-CN-YunxiNeural", "zh-CN-YunjianNeural")
JA_POOL = ("ja-JP-NanamiNeural", "ja-JP-KeitaNeural", "ja-JP-AoiNeural", "ja-JP-DaichiNeural")
VOCAL_LANGUAGE = {"dialogue": "ja", "inner_voice": "zh", "media_voice": "zh", "narration": "zh"}


class VoiceCastError(ValueError):
    pass


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
        language = str(item.get("language") or old.get("language") or "ja").lower()
        if language not in {"ja", "zh"}:
            raise VoiceCastError(f"{speaker_id}.language must be ja or zh")
        pool = JA_POOL if language == "ja" else ZH_POOL
        locked = bool(old.get("locked", item.get("locked", False)))
        voice = str(old.get("voice_id") or item.get("voice_id") or "") if locked else ""
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
        profile = {
            "speaker_id": speaker_id,
            "language": language,
            "provider": str(item.get("provider") or old.get("provider") or "edge"),
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
    expected = VOCAL_LANGUAGE.get(str(event.get("type") or ""))
    if expected and profile.get("language") != expected:
        raise VoiceCastError(
            f"{event.get('id')} requires {expected} voice but {profile.get('speaker_id')} is {profile.get('language')}"
        )
