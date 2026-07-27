"""Deterministic per-shot music direction and safe source automation."""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np


class MusicCueError(ValueError):
    """Raised when an authored music cue cannot be compiled safely."""


_MOODS = frozenset({"rnb", "dark", "ambient", "warm", "playful"})
_TRANSITIONS = frozenset({"crossfade", "cut", "stinger"})
_PROFILES = frozenset({"full", "thin", "pulse", "pad", "bass", "silence"})


def _bounded(value: Any, name: str, default: float) -> float:
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise MusicCueError(f"music_cue.{name} must be numeric") from exc
    if not 0.0 <= number <= 1.0:
        raise MusicCueError(f"music_cue.{name} must be between 0 and 1")
    return round(number, 4)


def _inferred(shot: dict[str, Any], default_mood: str) -> dict[str, Any]:
    func = (
        str(
            shot.get("dramatic_function")
            or (shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}).get(
                "dramatic_function"
            )
            or ""
        )
        .strip()
        .lower()
    )
    phase = str(shot.get("heat_phase") or "").strip().lower()
    if phase in {"act", "climax"} or func == "climax":
        return {
            "mood": "rnb" if default_mood != "dark" else "dark",
            "energy": 0.9,
            "density": 0.8,
            "bass_presence": 0.8,
            "brightness": 0.65,
            "stem_profile": "full",
        }
    if func in {"buildup", "rising_action", "crisis", "suspense"}:
        return {
            "mood": "dark",
            "energy": 0.7,
            "density": 0.55,
            "bass_presence": 0.7,
            "brightness": 0.25,
            "stem_profile": "pulse",
        }
    if func in {"intro", "establishing", "hook"}:
        return {
            "mood": "ambient",
            "energy": 0.35,
            "density": 0.2,
            "bass_presence": 0.2,
            "brightness": 0.4,
            "stem_profile": "pad",
        }
    if func in {"resolution", "falling_action", "afterglow"}:
        return {
            "mood": "warm",
            "energy": 0.35,
            "density": 0.25,
            "bass_presence": 0.25,
            "brightness": 0.55,
            "stem_profile": "thin",
        }
    return {
        "mood": default_mood,
        "energy": 0.55,
        "density": 0.45,
        "bass_presence": 0.5,
        "brightness": 0.5,
        "stem_profile": "full",
    }


def normalize_music_cue(
    raw: Any = None,
    *,
    shot: dict[str, Any] | None = None,
    default_mood: str = "rnb",
) -> dict[str, Any]:
    """Normalize a cue; explicit fields override dramaturgical inference."""
    shot = shot or {}
    base = _inferred(shot, default_mood if default_mood in _MOODS else "rnb")
    if raw is not None and not isinstance(raw, dict):
        raise MusicCueError("music_cue must be an object")
    raw = raw or {}
    cue = {**base, **raw}
    mood = str(cue.get("mood") or default_mood).strip().lower()
    if mood not in _MOODS:
        raise MusicCueError(f"music_cue.mood must be one of {sorted(_MOODS)}")
    transition = str(cue.get("transition") or "crossfade").strip().lower()
    if transition not in _TRANSITIONS:
        raise MusicCueError(f"music_cue.transition must be one of {sorted(_TRANSITIONS)}")
    profile = str(cue.get("stem_profile") or "full").strip().lower()
    if profile not in _PROFILES:
        raise MusicCueError(f"music_cue.stem_profile must be one of {sorted(_PROFILES)}")
    try:
        bpm = float(cue.get("bpm", 76.0))
    except (TypeError, ValueError) as exc:
        raise MusicCueError("music_cue.bpm must be numeric") from exc
    if not 40.0 <= bpm <= 180.0:
        raise MusicCueError("music_cue.bpm must be between 40 and 180")
    try:
        key_shift = int(cue.get("key_shift", 0))
    except (TypeError, ValueError) as exc:
        raise MusicCueError("music_cue.key_shift must be an integer") from exc
    if not -12 <= key_shift <= 12:
        raise MusicCueError("music_cue.key_shift must be between -12 and 12")
    motif = str(cue.get("motif_id") or f"{mood}:default").strip()
    if not motif or len(motif) > 80:
        raise MusicCueError("music_cue.motif_id must be 1-80 characters")
    try:
        seed = int(cue.get("take_seed", 0))
    except (TypeError, ValueError) as exc:
        raise MusicCueError("music_cue.take_seed must be an integer") from exc
    return {
        "mood": mood,
        "energy": _bounded(cue.get("energy"), "energy", 0.55),
        "density": _bounded(cue.get("density"), "density", 0.45),
        "bass_presence": _bounded(cue.get("bass_presence"), "bass_presence", 0.5),
        "brightness": _bounded(cue.get("brightness"), "brightness", 0.5),
        "duck_db": round(max(-18.0, min(0.0, float(cue.get("duck_db", 0.0)))), 2),
        "bpm": round(bpm, 2),
        "key_shift": key_shift,
        "stem_profile": profile,
        "motif_id": motif,
        "transition": transition,
        "seed": seed,
    }


def motif_seed(base_seed: int, motif_id: str, index: int) -> int:
    digest = hashlib.sha256(f"{base_seed}|{motif_id}".encode()).hexdigest()
    return (int(digest[:8], 16) + index) & 0x7FFFFFFF


def build_music_timeline(
    shots: list[dict[str, Any]],
    *,
    shot_starts: dict[str, float],
    shot_ends: dict[str, float],
    default_mood: str = "rnb",
) -> list[dict[str, Any]]:
    timeline = []
    for shot in shots:
        sid = str(shot.get("id"))
        if sid not in shot_starts or sid not in shot_ends:
            continue
        start, end = float(shot_starts[sid]), float(shot_ends[sid])
        if end <= start:
            continue
        cue = normalize_music_cue(shot.get("music_cue"), shot=shot, default_mood=default_mood)
        timeline.append({"shot_id": sid, "start_sec": start, "end_sec": end, **cue})
    return sorted(timeline, key=lambda item: item["start_sec"])


def summarize_music_timeline(timeline: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "shot_count": len(timeline),
        "moods": [item["mood"] for item in timeline],
        "motifs": [item["motif_id"] for item in timeline],
        "energy_curve": [item["energy"] for item in timeline],
        "density_curve": [item["density"] for item in timeline],
        "bass_presence_curve": [item["bass_presence"] for item in timeline],
        "brightness_curve": [item["brightness"] for item in timeline],
        "explainable": True,
        "source": "shot.music_cue with dramaturgical defaults",
    }


def apply_music_timeline_to_samples(
    samples: np.ndarray,
    *,
    sr: int,
    timeline: list[dict[str, Any]],
) -> np.ndarray:
    """Apply deterministic energy/duck automation to a supplied music file."""
    if not timeline:
        return samples
    out = samples.copy()
    total = len(out)
    for item in timeline:
        start = max(0, min(total, int(float(item["start_sec"]) * sr)))
        end = max(start, min(total, int(float(item["end_sec"]) * sr)))
        if end <= start:
            continue
        energy = float(item.get("energy", 0.55))
        gain = 0.72 + 0.48 * energy
        gain *= 10 ** (float(item.get("duck_db", 0.0)) / 20.0)
        profile = str(item.get("stem_profile") or "full")
        if profile == "thin":
            gain *= 0.72
        elif profile == "silence":
            gain = 0.0
        out[start:end] *= gain
    return out
