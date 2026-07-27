"""Validate the reusable short-drama designed-post packaging contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json

PACKAGE_FILE = "post-package.json"
SCHEMA_VERSION = 1
KIND = "short-drama-platform-package"
_TOP_LEVEL_KEYS = {
    "schema_version",
    "kind",
    "package_id",
    "intro",
    "outro",
    "captions",
    "safe_area",
}


class PlatformPackageError(ValueError):
    """A platform package cannot safely drive designed-post packaging."""


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise PlatformPackageError(f"{name} must be an object")
    return value


def _text(value: Any, name: str, *, required: bool = False) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise PlatformPackageError(f"{name} must be a non-empty string")
    return value.strip()


def _duration(value: Any, name: str, *, default: float) -> float:
    if value is None:
        return default
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PlatformPackageError(f"{name} must be numeric")
    duration = float(value)
    if not 0.4 <= duration <= 5.0:
        raise PlatformPackageError(f"{name} must be between 0.4 and 5 seconds")
    return round(duration, 3)


def load_platform_package(root: Path) -> dict[str, Any]:
    """Load an optional sidecar, returning deterministic overrides and receipt data."""
    path = root / PACKAGE_FILE
    if not path.is_file():
        return {
            "enabled": False,
            "source": None,
            "caption_policy": {
                "owner": "hyperframes",
                "theme": "default",
                "max_chars": 12,
                "languages": ["zh"],
            },
            "safe_area": {"top_pct": 10.0, "bottom_pct": 16.0},
            "overrides": {},
        }

    data = read_json(path)
    if not isinstance(data, dict):
        raise PlatformPackageError(f"{PACKAGE_FILE} must be a JSON object")
    unknown = sorted(set(data) - _TOP_LEVEL_KEYS)
    if unknown:
        raise PlatformPackageError(f"post-package.json has unknown keys: {', '.join(unknown)}")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise PlatformPackageError(f"post-package.json schema_version must be {SCHEMA_VERSION}")
    if data.get("kind", KIND) != KIND:
        raise PlatformPackageError(f"post-package.json kind must be {KIND!r}")

    package_id = _text(data.get("package_id"), "package_id", required=True)
    intro = _mapping(data.get("intro"), "intro")
    outro = _mapping(data.get("outro"), "outro")
    captions = _mapping(data.get("captions"), "captions")
    safe_area = _mapping(data.get("safe_area"), "safe_area")

    intro_mode = str(intro.get("mode") or "auto").strip().lower()
    if intro_mode not in {"auto", "short", "full", "none"}:
        raise PlatformPackageError("intro.mode must be auto|short|full|none")
    outro_mode = str(outro.get("mode") or "auto").strip().lower()
    if outro_mode not in {"auto", "hook", "cta", "full", "none"}:
        raise PlatformPackageError("outro.mode must be auto|hook|cta|full|none")
    title_duration_sec = _duration(intro.get("duration_sec"), "intro.duration_sec", default=1.2)
    end_duration_sec = _duration(outro.get("duration_sec"), "outro.duration_sec", default=1.8)
    max_chars = captions.get("max_chars", 12)
    if not isinstance(max_chars, int) or not 8 <= max_chars <= 20:
        raise PlatformPackageError("captions.max_chars must be an integer between 8 and 20")
    languages = captions.get("languages", ["zh"])
    if (
        not isinstance(languages, list)
        or not languages
        or any(x not in {"zh", "ja", "en"} for x in languages)
    ):
        raise PlatformPackageError("captions.languages must be a non-empty list of zh|ja|en")
    top = safe_area.get("top_pct", 10)
    bottom = safe_area.get("bottom_pct", 16)
    if not all(isinstance(x, (int, float)) for x in (top, bottom)) or not (
        0 <= top <= 25 and 0 <= bottom <= 25
    ):
        raise PlatformPackageError("safe_area top_pct and bottom_pct must be numbers from 0 to 25")
    if float(top) + float(bottom) > 35:
        raise PlatformPackageError("safe_area leaves too little picture area")

    title_sequence = {"mode": intro_mode}
    for key in ("subtitle", "tagline", "show_motifs"):
        if key in intro:
            title_sequence[key] = intro[key]
    end_roll = {"mode": outro_mode}
    for key in ("cta", "next_episode", "cast_heading", "crew_heading", "show_shot_list"):
        if key in outro:
            end_roll[key] = outro[key]
    return {
        "enabled": True,
        "source": PACKAGE_FILE,
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "package_id": package_id,
        "caption_policy": {
            "owner": "hyperframes",
            "theme": str(captions.get("theme") or "default"),
            "max_chars": max_chars,
            "languages": languages,
        },
        "safe_area": {"top_pct": float(top), "bottom_pct": float(bottom)},
        "timing": {
            "title_duration_sec": title_duration_sec,
            "end_duration_sec": end_duration_sec,
        },
        "overrides": {"title_sequence": title_sequence, "end_roll": end_roll},
    }


def assert_no_double_burn_override(root: Path, *, allow_burned_underlay: bool) -> dict[str, Any]:
    """Keep packaged platform episodes on the single-caption-owner contract."""
    package = load_platform_package(root)
    if package["enabled"] and allow_burned_underlay:
        raise PlatformPackageError(
            "post-package.json forbids --allow-burned-underlay: platform episodes have one caption owner"
        )
    return package
