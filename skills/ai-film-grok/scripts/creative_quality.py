#!/usr/bin/env python3
"""Creative-quality contract for the premium vertical production profile."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json

_PLACEHOLDERS = {
    "",
    "todo",
    "tbd",
    "待填写",
    "待补",
    "needs_authoring",
    "placeholder",
    "to be filled",
}


def _authored(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in _PLACEHOLDERS
    if isinstance(value, (list, tuple)):
        return bool(value) and all(_authored(item) for item in value)
    if isinstance(value, dict):
        return bool(value) and all(_authored(item) for item in value.values())
    return value is not None


def _issue(code: str, message: str, ref: str) -> dict[str, str]:
    return {"code": code, "message": message, "ref": ref}


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def validate_premium_vertical(root: Path | str) -> dict[str, Any]:
    """Validate authored intent without inventing content or human approval."""

    base = Path(root).expanduser().resolve()
    errors: list[dict[str, str]] = []
    graph = read_json(base / "drama-graph.json") or {}
    spec = read_json(base / "film-spec.json") or {}
    if not isinstance(graph, dict):
        errors.append(_issue("GRAPH_MISSING", "drama-graph.json is not an object", "graph"))
        graph = {}
    if not isinstance(spec, dict):
        errors.append(_issue("SPEC_MISSING", "film-spec.json is not an object", "spec"))
        spec = {}

    beats = graph.get("beats") or graph.get("beat_nodes") or []
    if not isinstance(beats, list) or not beats:
        errors.append(_issue("BEATS_MISSING", "authored beats are required", "beats"))
    else:
        for index, beat in enumerate(beats):
            if not isinstance(beat, dict):
                errors.append(_issue("BEAT_INVALID", "beat must be an object", f"beat[{index}]"))
                continue
            ref = str(beat.get("id") or f"beat[{index}]")
            for field in ("obstacle", "tactic", "turn", "outcome"):
                if not _authored(beat.get(field)):
                    errors.append(
                        _issue("BEAT_FIELD_MISSING", f"{field} must be authored", f"{ref}.{field}")
                    )
            visible = _first(beat, "state_delta", "visible_change", "start_state")
            end_state = _first(beat, "end_state", "state_after")
            if not _authored(visible) or ("start_state" in beat and not _authored(end_state)):
                errors.append(
                    _issue("BEAT_CHANGE_MISSING", "beat needs a visible state change", ref)
                )

    scenes = spec.get("scenes") or []
    shots = [
        shot for scene in scenes if isinstance(scene, dict) for shot in scene.get("shots") or []
    ]
    if not shots:
        errors.append(_issue("SHOTS_MISSING", "authored shots are required", "shots"))
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            errors.append(_issue("SHOT_INVALID", "shot must be an object", f"shot[{index}]"))
            continue
        ref = str(shot.get("id") or f"shot[{index}]")
        performance = shot.get("performance") if isinstance(shot.get("performance"), dict) else {}
        for field in ("subtext", "playable_action", "reaction_trigger"):
            value = _first(performance, field) if performance else shot.get(field)
            if not _authored(value):
                errors.append(
                    _issue(
                        "SHOT_PERFORMANCE_MISSING", f"{field} must be authored", f"{ref}.{field}"
                    )
                )
        dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
        for field in ("camera_axis", "shot_size", "lens_mm", "lighting"):
            if not _authored(dsl.get(field)):
                errors.append(
                    _issue("SHOT_CRAFT_MISSING", f"{field} must be authored", f"{ref}.dsl.{field}")
                )

    boards = [scene.get("director_board") for scene in scenes if isinstance(scene, dict)]
    if not boards or any(not isinstance(board, dict) for board in boards):
        errors.append(
            _issue(
                "DIRECTOR_BOARD_MISSING",
                "every scene needs an authored director_board",
                "scenes.director_board",
            )
        )
    else:
        for index, board in enumerate(boards):
            for field in ("emotional_turn", "visual_strategy", "performance_strategy"):
                if not _authored(board.get(field)):
                    errors.append(
                        _issue(
                            "DIRECTOR_BOARD_FIELD_MISSING",
                            f"{field} must be authored",
                            f"scene[{index}].director_board.{field}",
                        )
                    )

    return {
        "ok": not errors,
        "profile": "premium_vertical",
        "errors": errors,
        "checked": {
            "beats": len(beats) if isinstance(beats, list) else 0,
            "shots": len(shots),
            "scenes": len(scenes),
        },
        "human_review_required": True,
    }
