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

# These are arrangement instructions, not sample-pack identifiers.  Keeping the
# palette small makes a film sound like one score whose orchestration evolves,
# rather than a playlist that changes genre every shot.
_INSTRUMENT_PALETTES = {
    "ambient": ("felt_piano", "high_strings", "vibraphone"),
    "dark": ("low_strings", "prepared_piano", "frame_drum"),
    "warm": ("felt_piano", "warm_strings", "upright_bass"),
    "playful": ("pizzicato_strings", "marimba", "brush_drums"),
    "rnb": ("rhodes", "upright_bass", "brush_drums"),
}


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
            "motif_id": "heat:climax" if phase == "climax" or func == "climax" else "heat:act",
            "energy": 0.9,
            "density": 0.8,
            "bass_presence": 0.8,
            "brightness": 0.65,
            "stem_profile": "full",
        }
    if func in {"buildup", "rising_action", "crisis", "suspense"}:
        return {
            "mood": "dark",
            "motif_id": f"tension:{func}",
            "energy": 0.7,
            "density": 0.55,
            "bass_presence": 0.7,
            "brightness": 0.25,
            "stem_profile": "pulse",
        }
    if func in {"intro", "establishing", "hook"}:
        return {
            "mood": "ambient",
            "motif_id": f"arrival:{func}",
            "energy": 0.35,
            "density": 0.2,
            "bass_presence": 0.2,
            "brightness": 0.4,
            "stem_profile": "pad",
        }
    if func in {"resolution", "falling_action", "afterglow"}:
        return {
            "mood": "warm",
            "motif_id": f"release:{func}",
            "energy": 0.35,
            "density": 0.25,
            "bass_presence": 0.25,
            "brightness": 0.55,
            "stem_profile": "thin",
        }
    return {
        "mood": default_mood,
        "motif_id": f"{default_mood}:scene",
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
    if not 0 <= seed <= 0x7FFFFFFF:
        raise MusicCueError("music_cue.take_seed must be between 0 and 2147483647")
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


def _character_ids(shot: dict[str, Any]) -> list[str]:
    """Read common shot-plan cast projections without requiring a new schema field."""
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    for key in ("character_ids", "characterIds", "cast"):
        value = shot.get(key, dsl.get(key))
        if isinstance(value, list):
            ids = [str(item).strip() for item in value if str(item).strip()]
            if ids:
                return sorted(dict.fromkeys(ids))
    return []


def _story_motif(shot: dict[str, Any], cue: dict[str, Any]) -> str:
    """Prefer an authored motif; otherwise preserve character/pair recognition."""
    raw = shot.get("music_cue")
    if isinstance(raw, dict) and raw.get("motif_id"):
        return cue["motif_id"]
    cast = _character_ids(shot)
    if len(cast) >= 2:
        return f"pair:{'+'.join(cast[:2])}"
    if cast:
        return f"character:{cast[0]}"
    return cue["motif_id"]


def _instrument_palette(cue: dict[str, Any]) -> tuple[str, ...]:
    palette = _INSTRUMENT_PALETTES[cue["mood"]]
    profile = cue["stem_profile"]
    if profile == "silence":
        return ()
    if profile in {"pad", "thin"}:
        return palette[:2]
    if profile == "bass":
        return (palette[-1],)
    if profile == "pulse":
        return tuple(dict.fromkeys((palette[0], palette[-1])))
    return palette


def compile_music_cue(shot: dict[str, Any], *, default_mood: str = "rnb") -> dict[str, Any]:
    """Compile one shot's reviewable, instrumental-only music direction."""
    cue = normalize_music_cue(shot.get("music_cue"), shot=shot, default_mood=default_mood)
    cue["motif_id"] = _story_motif(shot, cue)
    return {
        **cue,
        "instrumental_only": True,
        "instrument_palette": list(_instrument_palette(cue)),
    }


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
        cue = compile_music_cue(shot, default_mood=default_mood)
        timeline.append(
            {
                "shot_id": sid,
                "start_sec": start,
                "end_sec": end,
                **cue,
            }
        )
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
        "bpm_curve": [item["bpm"] for item in timeline],
        "key_shift_curve": [item["key_shift"] for item in timeline],
        "take_seeds": [item["seed"] for item in timeline],
        "instrument_palettes": [item.get("instrument_palette", []) for item in timeline],
        "instrumental_only": all(item.get("instrumental_only") for item in timeline),
        "transitions": [item["transition"] for item in timeline],
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
