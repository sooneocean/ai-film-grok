#!/usr/bin/env python3
"""Normalize and compile per-line vocal performance cues.

The cue is intentionally provider-neutral.  Providers may support different
subsets, so compilation is deterministic and preserves unsupported fields in
the receipt instead of silently dropping the author's intent.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

EMOTIONS = frozenset(
    {
        "neutral",
        "calm",
        "happy",
        "sad",
        "angry",
        "fearful",
        "surprised",
        "teasing",
        "breathy",
        "whisper",
        "dominant",
        "needy",
        "tender",
        "excited",
        "crying",
        "laughing",
        "sensual",
    }
)

_PITCH_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?)(?:st|Hz|%)$")
_RATE_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?|slow|medium|fast)%?$")
_VOLUME_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d+)?)%$")


class PerformanceCueError(ValueError):
    pass


def _number(value: object, *, name: str, low: float, high: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise PerformanceCueError(f"performance_cue.{name} must be numeric") from exc
    if not low <= result <= high:
        raise PerformanceCueError(f"performance_cue.{name} must be between {low} and {high}")
    return result


def _string(raw: object, *, name: str, pattern: re.Pattern[str], default: str) -> str:
    if raw is None or str(raw).strip() == "":
        return default
    value = str(raw).strip()
    if not pattern.fullmatch(value):
        raise PerformanceCueError(f"performance_cue.{name} has invalid value {value!r}")
    return value


def normalize_performance_cue(raw: object = None, *, tone_tags: object = None) -> dict[str, Any]:
    """Return a stable cue; missing values preserve current neutral behavior."""
    source = raw if isinstance(raw, Mapping) else {}
    emotion = str(source.get("emotion") or "neutral").strip().lower()
    if emotion not in EMOTIONS:
        raise PerformanceCueError(
            f"performance_cue.emotion must be one of {sorted(EMOTIONS)}; got {emotion!r}"
        )
    delivery_raw = source.get("delivery", tone_tags if tone_tags is not None else [])
    if isinstance(delivery_raw, str):
        delivery = [
            x.strip().lower() for x in delivery_raw.replace("，", ",").split(",") if x.strip()
        ]
    elif isinstance(delivery_raw, (list, tuple)):
        delivery = [str(x).strip().lower() for x in delivery_raw if str(x).strip()]
    else:
        delivery = []
    pauses_raw = source.get("pauses_ms", [])
    if isinstance(pauses_raw, (int, float, str)):
        pauses_raw = [pauses_raw]
    if not isinstance(pauses_raw, (list, tuple)):
        raise PerformanceCueError("performance_cue.pauses_ms must be a list")
    pauses: list[int] = []
    for value in pauses_raw:
        try:
            ms = int(value)
        except (TypeError, ValueError) as exc:
            raise PerformanceCueError("performance_cue.pauses_ms must contain integers") from exc
        if not 0 <= ms <= 3000:
            raise PerformanceCueError("performance_cue.pauses_ms values must be 0..3000")
        pauses.append(ms)
    pronunciation = source.get("pronunciation", {})
    if not isinstance(pronunciation, Mapping):
        raise PerformanceCueError("performance_cue.pronunciation must be an object")
    seed = source.get("take_seed", 0)
    try:
        seed = int(seed)
    except (TypeError, ValueError) as exc:
        raise PerformanceCueError("performance_cue.take_seed must be an integer") from exc
    # Film Production OS W7 · optional acting-layer fields (director language)
    def _opt_str(key: str) -> str | None:
        val = str(source.get(key) or "").strip()
        return val or None

    tempo_raw = source.get("tempo")
    tempo: str | None
    if tempo_raw is None or str(tempo_raw).strip() == "":
        tempo = None
    else:
        tempo = str(tempo_raw).strip().lower()
        if tempo not in {"slow", "medium", "fast", "held", "rush"}:
            raise PerformanceCueError(
                "performance_cue.tempo must be one of slow|medium|fast|held|rush"
            )

    return {
        "emotion": emotion,
        "intensity": round(
            _number(source.get("intensity", 0.0), name="intensity", low=0.0, high=1.0), 3
        ),
        "rate": _string(source.get("rate"), name="rate", pattern=_RATE_RE, default="+0%"),
        "pitch": _string(source.get("pitch"), name="pitch", pattern=_PITCH_RE, default="+0Hz"),
        "volume": _string(source.get("volume"), name="volume", pattern=_VOLUME_RE, default="+0%"),
        "delivery": list(dict.fromkeys(delivery)),
        "pauses_ms": pauses,
        "pronunciation": {str(k): str(v) for k, v in pronunciation.items()},
        "language": str(source.get("language") or "").strip().lower() or None,
        "take_seed": seed,
        "source": str(source.get("source") or "shot/default"),
        # W7 acting layer (optional; providers may ignore)
        "objective": _opt_str("objective"),
        "subtext": _opt_str("subtext"),
        "eye": _opt_str("eye"),
        "breath": _opt_str("breath"),
        "tempo": tempo,
    }


def compile_edge(cue: Mapping[str, Any], text: str) -> dict[str, Any]:
    """Compile to safe Edge parameters plus an auditable SSML representation."""
    c = normalize_performance_cue(cue)
    body = str(text).strip()
    pauses = list(c["pauses_ms"])
    # edge-tts escapes text internally; punctuation is the portable pause cue.
    if pauses:
        pieces = re.split(r"([，。！？；：,.!?;:])", body)
        rebuilt: list[str] = []
        for i, piece in enumerate(pieces):
            rebuilt.append(piece)
            if i < len(pauses) * 2 - 1 and piece.strip():
                rebuilt.append("…" if pauses[i // 2] >= 500 else ",")
        body = "".join(rebuilt)
    ssml = (
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis">'
        f'<prosody rate="{c["rate"]}" pitch="{c["pitch"]}" volume="{c["volume"]}">'
        f"{body}</prosody></speak>"
    )
    return {
        "backend": "edge",
        "text": body,
        "rate": c["rate"],
        "pitch": c["pitch"],
        "volume": c["volume"],
        "ssml": ssml,
        "unsupported": [x for x in c["delivery"] if x not in {"whisper_start"}],
        "cue": c,
    }


def compile_instruction(cue: Mapping[str, Any]) -> str:
    c = normalize_performance_cue(cue)
    delivery = ", ".join(c["delivery"]) or "natural delivery"
    pauses = ", ".join(f"{x}ms" for x in c["pauses_ms"]) or "natural pauses"
    return (
        f"Emotion: {c['emotion']}; intensity: {c['intensity']:.2f}; "
        f"delivery: {delivery}; rate: {c['rate']}; pitch: {c['pitch']}; "
        f"volume: {c['volume']}; pauses: {pauses}."
    )


def cue_hash(cue: Mapping[str, Any]) -> str:
    payload = json.dumps(normalize_performance_cue(cue), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summarize_bgm_response(shots: object) -> dict[str, Any]:
    """Derive deterministic, explainable BGM response settings from shot cues."""
    cues: list[dict[str, Any]] = []
    if isinstance(shots, list):
        for shot in shots:
            if isinstance(shot, Mapping):
                cues.append(
                    normalize_performance_cue(
                        shot.get("performance_cue"), tone_tags=shot.get("tone_tags")
                    )
                )
    if not cues:
        return {
            "shots": 0,
            "mean_intensity": 0.0,
            "music_gain": 1.0,
            "duck_db": -2.0,
            "tail_ms": 300,
        }
    mean = sum(float(c["intensity"]) for c in cues) / len(cues)
    breathy = sum(
        1 for c in cues if "breathy" in c["delivery"] or c["emotion"] in {"whisper", "breathy"}
    )
    return {
        "shots": len(cues),
        "mean_intensity": round(mean, 3),
        "music_gain": round(max(0.82, 1.0 - mean * 0.12), 3),
        "duck_db": round(-2.0 - mean * 4.0, 2),
        "tail_ms": 800 if mean >= 0.7 else (500 if mean >= 0.35 else 300),
        "breathy_share": round(breathy / len(cues), 3),
        "rule": "performance intensity lowers BGM gain and deepens VO duck; breathy/whisper cues keep longer tail",
    }
