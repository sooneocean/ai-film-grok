"""Deterministic planning for ACE-Step music edits and harmonic continuity."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any


class MusicEditorError(ValueError):
    pass


_PITCH_CLASS = {
    "C": 0,
    "B#": 0,
    "C#": 1,
    "DB": 1,
    "D": 2,
    "D#": 3,
    "EB": 3,
    "E": 4,
    "FB": 4,
    "E#": 5,
    "F": 5,
    "F#": 6,
    "GB": 6,
    "G": 7,
    "G#": 8,
    "AB": 8,
    "A": 9,
    "A#": 10,
    "BB": 10,
    "B": 11,
    "CB": 11,
}
_CANONICAL_SHARP = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_CAMELOT_MAJOR = {11: 1, 6: 2, 1: 3, 8: 4, 3: 5, 10: 6, 5: 7, 0: 8, 7: 9, 2: 10, 9: 11, 4: 12}
_CAMELOT_MINOR = {8: 1, 3: 2, 10: 3, 5: 4, 0: 5, 7: 6, 2: 7, 9: 8, 4: 9, 11: 10, 6: 11, 1: 12}
_KEY_RE = re.compile(r"^\s*([A-Ga-g])([#b♯♭]?)(?:\s*(major|minor|maj|min|m))?\s*$", re.I)
_EDIT_VARIANTS = frozenset({"exact", "dialogue-safe", "loop", "outro"})


def normalize_keyscale(value: Any) -> dict[str, Any]:
    raw = str(value or "").replace("♯", "#").replace("♭", "b").strip()
    match = _KEY_RE.match(raw)
    if not match:
        return {"label": raw, "pitch_class": None, "mode": "", "camelot": ""}
    note = (match.group(1) + match.group(2)).upper()
    pitch_class = _PITCH_CLASS.get(note)
    suffix = (match.group(3) or "major").lower()
    mode = "minor" if suffix in {"minor", "min", "m"} else "major"
    if pitch_class is None:
        return {"label": raw, "pitch_class": None, "mode": "", "camelot": ""}
    wheel = (_CAMELOT_MINOR if mode == "minor" else _CAMELOT_MAJOR)[pitch_class]
    return {
        "label": f"{_CANONICAL_SHARP[pitch_class]} {mode}",
        "pitch_class": pitch_class,
        "mode": mode,
        "camelot": f"{wheel}{'A' if mode == 'minor' else 'B'}",
    }


def harmonic_compatibility(left: Any, right: Any) -> dict[str, Any]:
    source = normalize_keyscale(left)
    target = normalize_keyscale(right)
    if source["pitch_class"] is None or target["pitch_class"] is None:
        return {
            "compatible": False,
            "relation": "unknown",
            "score": 0.0,
            "source": source,
            "target": target,
        }
    if source["pitch_class"] == target["pitch_class"] and source["mode"] == target["mode"]:
        relation, score = "same", 1.0
    else:
        source_wheel = int(str(source["camelot"])[:-1])
        target_wheel = int(str(target["camelot"])[:-1])
        source_mode = str(source["camelot"])[-1]
        target_mode = str(target["camelot"])[-1]
        wheel_distance = min(
            (source_wheel - target_wheel) % 12,
            (target_wheel - source_wheel) % 12,
        )
        if source_wheel == target_wheel and source_mode != target_mode:
            relation, score = "relative", 0.95
        elif source_mode == target_mode and wheel_distance == 1:
            relation, score = "adjacent", 0.85
        else:
            relation, score = "distant", 0.0
    return {
        "compatible": score > 0,
        "relation": relation,
        "score": score,
        "source": source,
        "target": target,
    }


def _tempo_compatibility(left: Any, right: Any) -> dict[str, Any]:
    try:
        source = float(left)
        target = float(right)
    except (TypeError, ValueError):
        return {"compatible": False, "relation": "unknown", "delta": 1.0}
    if source <= 0 or target <= 0:
        return {"compatible": False, "relation": "unknown", "delta": 1.0}
    candidates = (
        ("same", target),
        ("half_time", target * 2.0),
        ("double_time", target / 2.0),
    )
    relation, adjusted = min(candidates, key=lambda item: abs(item[1] - source) / source)
    delta = abs(adjusted - source) / source
    return {
        "compatible": delta <= 0.12,
        "relation": relation if delta <= 0.12 else "mismatch",
        "delta": round(delta, 6),
    }


def _beats_per_bar(value: Any) -> int:
    try:
        numerator = int(str(value or "4/4").split("/", 1)[0])
    except (TypeError, ValueError):
        numerator = 4
    return max(2, min(12, numerator))


def plan_transition(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    requested = str(current.get("transition") or "crossfade").strip().lower()
    if previous is None:
        return {
            "mode": "cold_open",
            "requested": requested,
            "duration_sec": 0.0,
            "align": "first_frame",
            "generation_required": False,
            "reason": "first_cue",
        }
    if requested == "cut":
        return {
            "mode": "cut",
            "requested": requested,
            "duration_sec": 0.0,
            "align": "next_downbeat",
            "generation_required": False,
            "reason": "authored_cut",
        }
    if requested == "stinger":
        return {
            "mode": "stinger",
            "requested": requested,
            "duration_sec": 0.8,
            "align": "hit_point",
            "generation_required": False,
            "approved_stinger_required": True,
            "reason": "authored_stinger",
        }
    harmonic = harmonic_compatibility(previous.get("keyscale"), current.get("keyscale"))
    tempo = _tempo_compatibility(previous.get("bpm"), current.get("bpm"))
    try:
        bpm = max(40.0, min(180.0, float(current.get("bpm") or 76.0)))
    except (TypeError, ValueError):
        bpm = 76.0
    two_bars = 2.0 * _beats_per_bar(current.get("timesignature")) * 60.0 / bpm
    duration = round(max(4.0, min(8.0, two_bars)), 3)
    if harmonic["compatible"] and tempo["compatible"]:
        mode, reason, generation = "beat_crossfade", "harmonic_and_tempo_match", False
    elif harmonic["compatible"]:
        mode, reason, generation = "tempo_bridge", "tempo_mismatch", True
    elif tempo["compatible"]:
        mode, reason, generation = "repaint_bridge", "harmonic_mismatch", True
    else:
        mode, reason, generation = "repaint_bridge", "harmonic_and_tempo_mismatch", True
    return {
        "mode": mode,
        "requested": requested,
        "duration_sec": duration,
        "align": "bar",
        "generation_required": generation,
        "reason": reason,
        "harmonic": harmonic,
        "tempo": tempo,
    }


def _edit_strategy(target: float, source: float) -> str:
    if target < source - 3.0:
        return "cover_cutdown"
    if target > source + 0.001:
        return "loop_then_repaint_outro"
    if abs(target - source) > 0.001:
        return "repaint_outro"
    return "exact_master"


def build_music_edit_plan(selection_receipt: dict[str, Any]) -> dict[str, Any]:
    if selection_receipt.get("schema") != "aifilm-bgm-selection-v1":
        raise MusicEditorError("invalid BGM selection receipt")
    selections = selection_receipt.get("selections")
    if not isinstance(selections, list):
        raise MusicEditorError("BGM selection receipt requires selections")
    edits: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    requirements: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for raw in selections:
        if not isinstance(raw, dict):
            raise MusicEditorError("BGM selection must be an object")
        target = float(raw.get("end_sec") or 0.0) - float(raw.get("start_sec") or 0.0)
        source = float(raw.get("duration_sec") or 0.0)
        if target <= 0 or source <= 0:
            raise MusicEditorError("BGM selection durations must be positive")
        dialogue_safe_requested = (
            bool(raw.get("dialogue_present")) or float(raw.get("duck_db") or 0.0) <= -3
        )
        dialogue_safe_missing = dialogue_safe_requested and not bool(raw.get("dialogue_safe"))
        strategy = _edit_strategy(target, source)
        edit_required = strategy != "exact_master" or dialogue_safe_missing
        edit = {
            "shot_id": str(raw.get("shot_id") or ""),
            "asset_id": str(raw.get("asset_id") or ""),
            "asset_sha256": str(raw.get("sha256") or ""),
            "source_path": str(raw.get("path") or ""),
            "source_duration_sec": round(source, 3),
            "target_duration_sec": round(target, 3),
            "strategy": strategy,
            "dialogue_safe_required": dialogue_safe_requested,
            "dialogue_safe_satisfied": not dialogue_safe_missing,
            "raw_truncation_allowed": False,
            "offline_generation_required": edit_required,
            "approval_required": edit_required,
        }
        supplied_transition = raw.get("transition_plan")
        transition = {
            "shot_id": edit["shot_id"],
            **(
                dict(supplied_transition)
                if isinstance(supplied_transition, dict)
                else plan_transition(previous, raw)
            ),
        }
        edits.append(edit)
        transitions.append(transition)
        if edit_required:
            variants = []
            if strategy != "exact_master":
                variants.append("exact")
            if dialogue_safe_missing:
                variants.append("dialogue-safe")
            requirements.append(
                {
                    "kind": "approved_edit_variant",
                    "shot_id": edit["shot_id"],
                    "asset_id": edit["asset_id"],
                    "target_duration_sec": edit["target_duration_sec"],
                    "variants": variants,
                }
            )
        if transition.get("generation_required"):
            requirements.append(
                {
                    "kind": "approved_transition_bridge",
                    "shot_id": edit["shot_id"],
                    "from_asset_id": str((previous or {}).get("asset_id") or ""),
                    "to_asset_id": edit["asset_id"],
                    "duration_sec": transition["duration_sec"],
                }
            )
        previous = raw
    payload = {
        "schema": "aifilm-music-edit-plan-v1",
        "film_id": str(selection_receipt.get("film_id") or ""),
        "catalog_revision": int(selection_receipt.get("catalog_revision") or 0),
        "catalog_sha256": str(selection_receipt.get("catalog_sha256") or ""),
        "approved_assets_only": True,
        "generation_phase": "offline_curation",
        "ready_for_final": not requirements,
        "requirements": requirements,
        "edits": edits,
        "transitions": transitions,
    }
    payload["plan_sha256"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


def _base_recipe(
    parent: dict[str, Any],
    *,
    parent_path: Path,
    duration: float,
) -> dict[str, Any]:
    if not 10.0 <= duration <= 600.0:
        raise MusicEditorError("ACE-Step edit duration must be between 10 and 600 seconds")
    asset_id = str(parent.get("asset_id") or "").strip()
    if not asset_id:
        raise MusicEditorError("approved parent asset_id is required")
    return {
        "mood": str(parent.get("mood") or "rnb"),
        "dramatic_tags": list(parent.get("dramatic_tags") or []),
        "energy": float(parent.get("energy") or 0.5),
        "stem_profile": str(parent.get("stem_profile") or "full"),
        "bpm": parent.get("bpm"),
        "keyscale": str(parent.get("keyscale") or ""),
        "timesignature": str(parent.get("timesignature") or "4/4"),
        "duration": float(duration),
        "motif_family": str(parent.get("motif_family") or ""),
        "series_id": str(parent.get("series_id") or ""),
        "parent_asset_id": asset_id,
        "reference_audio": str(parent_path),
        "approval_required": True,
        "generation_phase": "offline_curation",
    }


def edit_variant_recipes(
    parent: dict[str, Any],
    *,
    parent_path: Path,
    target_duration: float,
    variants: Iterable[str],
) -> list[dict[str, Any]]:
    requested = tuple(dict.fromkeys(str(item).strip().lower() for item in variants))
    unknown = set(requested) - _EDIT_VARIANTS
    if unknown or not requested:
        raise MusicEditorError("edit variants must be exact|dialogue-safe|loop|outro")
    base = _base_recipe(parent, parent_path=parent_path, duration=float(target_duration))
    asset_id = str(parent["asset_id"])
    prompts = {
        "exact": (
            "instrumental exact-duration cinematic cutdown preserving the supplied motif, "
            "immediate musical entrance, complete final cadence, no vocals"
        ),
        "dialogue-safe": (
            "instrumental dialogue-safe arrangement of the supplied motif, sparse center, "
            "restrained lead, reduced midrange density, gentle bass and percussion, no vocals"
        ),
        "loop": (
            "instrumental seamless loop arrangement of the supplied motif, stable middle bed, "
            "matching beginning and ending texture, no final cadence, no vocals"
        ),
        "outro": (
            "repair only the ending into a complete musical cadence, preserve the supplied "
            "motif and arrangement, no vocals"
        ),
    }
    recipes = []
    for variant in requested:
        recipe = {
            **base,
            "recipe_id": f"edit-{asset_id}-{variant}-{int(round(target_duration))}s",
            "edit_variant": variant,
            "task_type": "repaint" if variant == "outro" else "cover",
            "cover_strength": 0.82 if variant in {"exact", "outro"} else 0.7,
            "dialogue_safe": variant == "dialogue-safe",
            "loopable": variant == "loop",
            "prompt": prompts[variant],
        }
        if variant == "outro":
            recipe["repainting_start"] = round(max(0.0, float(target_duration) - 8.0), 3)
            recipe["repainting_end"] = float(target_duration)
        recipes.append(recipe)
    return recipes


def motif_development_recipes(
    parent: dict[str, Any],
    *,
    parent_path: Path,
) -> list[dict[str, Any]]:
    base = _base_recipe(parent, parent_path=parent_path, duration=60.0)
    motif = str(parent.get("motif_family") or "").strip()
    series_id = str(parent.get("series_id") or "").strip()
    if not motif or not series_id:
        raise MusicEditorError("motif development requires motif_family and series_id")
    roles = (
        ("statement", 0.58, "full", "clear complete first statement"),
        ("fragment", 0.24, "thin", "brief incomplete fragments and restrained spacing"),
        ("tender", 0.34, "pad", "gentle intimate reharmonization"),
        ("corrupted", 0.68, "pulse", "dark destabilized harmony and uneasy pulse"),
        ("reveal", 0.76, "full", "expanding orchestration and decisive reveal"),
        ("loss", 0.3, "thin", "hollow unresolved grieving variation"),
        ("reunion", 0.64, "full", "warm restored harmony and emotional return"),
        ("climax", 0.92, "full", "maximum dramatic development and resolved cadence"),
    )
    recipes = []
    for role, energy, profile, direction in roles:
        recipes.append(
            {
                **base,
                "recipe_id": f"motif-{series_id}-{motif}-{role}",
                "motif_role": role,
                "energy": energy,
                "stem_profile": profile,
                "task_type": "cover",
                "cover_strength": 0.76,
                "prompt": (
                    f"instrumental {direction} of the supplied {motif} motif, "
                    "cinematic, dialogue-safe mix, no vocals"
                ),
            }
        )
    return recipes


def transition_bridge_recipe(
    outgoing: dict[str, Any],
    incoming: dict[str, Any],
    *,
    outgoing_path: Path,
    duration: float = 10.0,
) -> dict[str, Any]:
    base = _base_recipe(outgoing, parent_path=outgoing_path, duration=float(duration))
    outgoing_id = str(outgoing.get("asset_id") or "")
    incoming_id = str(incoming.get("asset_id") or "")
    if not incoming_id:
        raise MusicEditorError("transition bridge requires an approved incoming asset")
    return {
        **base,
        "recipe_id": f"bridge-{outgoing_id}-to-{incoming_id}-{int(round(duration))}s",
        "edit_variant": "bridge",
        "transition_to_asset_id": incoming_id,
        "dialogue_safe": True,
        "task_type": "cover",
        "cover_strength": 0.74,
        "bpm": incoming.get("bpm") or outgoing.get("bpm"),
        "keyscale": str(incoming.get("keyscale") or outgoing.get("keyscale") or ""),
        "timesignature": str(incoming.get("timesignature") or "4/4"),
        "prompt": (
            "instrumental cinematic transition bridge preserving the outgoing motif, "
            f"arriving naturally in {incoming.get('keyscale') or 'the target key'} at "
            f"{incoming.get('bpm') or 'the target'} BPM, complete handoff, no vocals"
        ),
    }
