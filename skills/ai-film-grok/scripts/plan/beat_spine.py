"""Beat spine loader — external JSON configuration for beat spines.

Replaces hardcoded spine lists in story_plan.py with file-based config.
New spine types can be added by dropping a JSON file into the schemas directory
without modifying Python code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas" / "beat-spines"  # skill root

# Canonical spine names and their JSON file names
SPINE_FILES: dict[str, str] = {
    "default": "default.json",
    "adult_max": "adult_max.json",
    "hardcore_male": "hardcore_male.json",
    "dual_climax": "dual_climax.json",
}


def _load_spine(name: str, filename: str) -> list[dict[str, Any]]:
    path = SCHEMA_DIR / filename
    if not path.is_file():
        raise FileNotFoundError(f"beat spine file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"beat spine {name} must be a JSON array, got {type(data).__name__}")
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"beat spine {name}[{i}] must be an object")
        if "key" not in item:
            raise ValueError(f"beat spine {name}[{i}] missing required key 'key'")
    return data


def load_spine(name: str) -> list[dict[str, Any]]:
    """Load a beat spine by canonical name.

    Supported names: default, adult_max, hardcore_male, dual_climax,
    and any genre name that has a corresponding JSON file (drama, mystery, etc.).
    """
    filename = SPINE_FILES.get(name)
    if filename:
        return _load_spine(name, filename)
    # Try genre spine file directly
    filename = f"{name}.json"
    return _load_spine(name, filename)


def list_spines() -> list[str]:
    """Return all available spine names (canonical + genre names)."""
    names = list(SPINE_FILES.keys())
    for f in sorted(SCHEMA_DIR.glob("*.json")):
        stem = f.stem
        if stem not in names:
            names.append(stem)
    return names


def spine_exists(name: str) -> bool:
    """Check whether a spine file exists for the given name."""
    filename = SPINE_FILES.get(name) or f"{name}.json"
    return (SCHEMA_DIR / filename).is_file()
