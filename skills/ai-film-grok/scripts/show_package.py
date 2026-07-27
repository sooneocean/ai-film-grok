"""Validate a reusable short-drama show package for designed post-production."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from util import read_json

SHOW_PACKAGE_FILE = "show-package.json"
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ShowPackageError(ValueError):
    """A show package is malformed and must not drive a renderer."""


def _mapping(value: Any, name: str, *, required: bool = False) -> dict[str, Any]:
    if value is None and not required:
        return {}
    if not isinstance(value, dict):
        raise ShowPackageError(f"{name} must be an object")
    return value


def _text(value: Any, name: str, *, required: bool = False) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise ShowPackageError(f"{name} must be a non-empty string")
    return value.strip()


def _duration(value: Any, name: str, default: float) -> float:
    if value is None:
        return default
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ShowPackageError(f"{name} must be a number")
    result = float(value)
    if not 0.2 <= result <= 10.0:
        raise ShowPackageError(f"{name} must be between 0.2 and 10 seconds")
    return result


def _validate(value: Any) -> dict[str, Any]:
    data = _mapping(value, "show_package", required=True)
    package_id = _text(data.get("id"), "id", required=True)
    version = _text(data.get("version"), "version", required=True)
    brand = _mapping(data.get("brand"), "brand")
    opening = _mapping(data.get("opening"), "opening")
    captions = _mapping(data.get("captions"), "captions")
    ending = _mapping(data.get("ending"), "ending")

    accent = _text(brand.get("accent"), "brand.accent")
    if accent and not _HEX_COLOR.fullmatch(accent):
        raise ShowPackageError("brand.accent must be a #RRGGBB color")
    safe_bottom = captions.get("safe_bottom_px", 0)
    if (
        not isinstance(safe_bottom, int)
        or isinstance(safe_bottom, bool)
        or not 0 <= safe_bottom <= 600
    ):
        raise ShowPackageError("captions.safe_bottom_px must be an integer between 0 and 600")

    return {
        "id": package_id,
        "version": version,
        "brand": {"label": _text(brand.get("label"), "brand.label"), "accent": accent},
        "opening": {
            "duration_sec": _duration(opening.get("duration_sec"), "opening.duration_sec", 1.5),
            "series_title": _text(opening.get("series_title"), "opening.series_title"),
            "episode": _text(opening.get("episode"), "opening.episode"),
        },
        "captions": {
            "identity": _text(captions.get("identity"), "captions.identity"),
            "safe_bottom_px": safe_bottom,
        },
        "ending": {
            "duration_sec": _duration(ending.get("duration_sec"), "ending.duration_sec", 1.5),
            "cta": _text(ending.get("cta"), "ending.cta"),
            "next_episode_hook": _text(ending.get("next_episode_hook"), "ending.next_episode_hook"),
        },
    }


def resolve_show_package(root: Path, spec: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve inline package first, then the film-root sidecar, without merging them."""
    inline = spec.get("show_package") if isinstance(spec, dict) else None
    if inline is not None:
        return _validate(inline)
    path = Path(root).expanduser().resolve() / SHOW_PACKAGE_FILE
    if not path.is_file():
        return None
    data = read_json(path)
    if data is None:
        raise ShowPackageError(f"could not read {path}")
    return _validate(data)
