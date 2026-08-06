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


# Vocal event types that carry TTS language (mirrors audio_timeline.VOCAL_TYPES; kept
# local to avoid an import cycle with audio_timeline).
_TTS_VOCAL_TYPES = frozenset({"dialogue", "inner_voice", "media_voice", "narration"})


def _event_lang_safe(event: dict[str, Any]) -> str:
    """Resolve language, never raising — falls back to the raw explicit value."""
    try:
        return event_language(event)
    except Exception:  # noqa: BLE001 - retired-ja / unsupported still yields a code
        raw = (
            event.get("language")
            or event.get("spoken_lang")
            or event.get("dialogue_spoken_lang")
            or "?"
        )
        return str(raw).strip().lower() or "?"


def _is_pingpong(seq: list[str]) -> bool:
    """True for an A,B,A,B… oscillation over >=4 events (exactly two distinct langs)."""
    if len(seq) < 4 or len(set(seq)) != 2:
        return False
    return all(seq[i] != seq[i + 1] for i in range(len(seq) - 1))


def detect_language_pingpong(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """P0-5: flag unjustified TTS language ping-pong (references/lessons-2026-07-23-…).

    Adjacent TTS language flips must be explained by a speaker-layer change. We flag:
      * TTS_LANG_FLIP_NO_SPEAKER_CHANGE — consecutive vocal events with different
        languages but the *same* speaker (no layer change to justify the flip).
      * TTS_LANG_PINGPONG — a single speaker's language oscillates A,B,A,B… (>=4).

    Japanese is retired (zh-only), so ``event_language`` raises on ``ja``; we still
    capture the offending raw code via ``_event_lang_safe`` so the flip is reported.
    """
    issues: list[dict[str, Any]] = []
    vocal = [
        e
        for e in (events or [])
        if isinstance(e, dict) and str(e.get("type") or "").lower() in _TTS_VOCAL_TYPES
    ]
    seqs = [_event_lang_safe(e) for e in vocal]

    # Consecutive same-speaker flips.
    for i in range(1, len(vocal)):
        la, lb = seqs[i - 1], seqs[i]
        if la == lb:
            continue
        sa = str(vocal[i - 1].get("speaker") or vocal[i - 1].get("speaker_id") or "").strip().lower()
        sb = str(vocal[i].get("speaker") or vocal[i].get("speaker_id") or "").strip().lower()
        if sa and sa == sb:
            issues.append(
                {
                    "code": "TTS_LANG_FLIP_NO_SPEAKER_CHANGE",
                    "severity": "warning",
                    "message": (
                        f"same speaker '{sa}' flips TTS language {la}→{lb} "
                        "without a speaker-layer change (references: 成块切换，speaker 可解释)"
                    ),
                    "speaker": sa,
                }
            )

    # Per-speaker oscillation (A,B,A,B…).
    by_speaker: dict[str, list[str]] = {}
    for e, lang in zip(vocal, seqs, strict=False):
        s = str(e.get("speaker") or e.get("speaker_id") or "").strip().lower() or "__none__"
        by_speaker.setdefault(s, []).append(lang)
    for s, seq in by_speaker.items():
        if _is_pingpong(seq):
            issues.append(
                {
                    "code": "TTS_LANG_PINGPONG",
                    "severity": "warning",
                    "message": (
                        f"speaker '{s}' oscillates TTS language {seq[:6]} "
                        "(ping-pong; must be block-level switching)"
                    ),
                    "speaker": s,
                }
            )
    return issues


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
