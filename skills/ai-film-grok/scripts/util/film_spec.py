"""Shared film-spec helpers used across the pipeline.

``_load_spec`` raises ``FilmError`` on missing/invalid input — callers that
prefer a soft fallback should wrap in try/except or use ``soft_load_spec``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import require_json, soft_json
from util.errors import FilmError


def _root(path: Path | str) -> Path:
    """Expand user tilde and resolve to absolute path."""
    return Path(path).expanduser().resolve()


def _load_spec(root: Path) -> dict[str, Any]:
    """Load film-spec.json strictly — raises FilmError on missing or invalid."""
    data = require_json(root / "film-spec.json")
    if not isinstance(data, dict):
        raise FilmError("film-spec.json is missing or invalid")
    return data


def soft_load_spec(root: Path) -> dict[str, Any]:
    """Load film-spec.json softly — returns ``{}`` on missing or invalid.

    C6.4/C5.3: must use util.soft_json (not util.json_io.read_json which is strict).
    """
    return soft_json(root / "film-spec.json")


def _iter_shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Iterate all shots from a film spec, skipping malformed scenes/shots."""
    shots: list[dict[str, Any]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if isinstance(shot, dict) and shot.get("id"):
                shots.append(shot)
    return shots


__all__ = ["_root", "_load_spec", "soft_load_spec", "_iter_shots"]
