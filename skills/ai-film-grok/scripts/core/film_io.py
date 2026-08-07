"""Manifest / director-notes / film directory tree I/O."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.constants import DIRECTOR_NOTES_NAME, GATE_ORDER, MANIFEST_NAME, SCHEMA_VERSION
from plan.director_review import empty_director_notes
from util import require_json as read_json
from util import utc_now, write_json
from util.errors import FilmError
from util.security_policy import SecurityPolicyError, safe_workspace_directory
from util.validators import aspect_dims


def film_dirs(root: Path) -> dict[str, Path]:
    dirs = {"root": root}
    try:
        for name in ("prompts", "canonical", "keyframes", "clips", "audio", "out", "receipts"):
            dirs[name] = safe_workspace_directory(root, name, field=f"film {name} directory")
    except SecurityPolicyError as exc:
        raise FilmError(str(exc)) from exc
    return dirs


def ensure_tree(root: Path) -> None:
    for path in film_dirs(root).values():
        path.mkdir(parents=True, exist_ok=True)


def empty_manifest(*, title: str, theme: str, aspect: str) -> dict[str, Any]:
    w, h = aspect_dims(aspect)
    return {
        "schema_version": SCHEMA_VERSION,
        "provider_default": "grok-imagine",
        "title": title,
        "theme": theme,
        "aspect_ratio": aspect,
        "width": w,
        "height": h,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "truth_contract": {
            "source_of_truth": "local-contract-and-receipts",
            "contract_sha256": "",
            "graph_sha256": "",
            "spec_sha256": "",
            "timeline_sha256": "",
        },
        "style_locked": False,
        "stills": {},
        "clips": {},
        "gates": {name: name == "brief" for name in GATE_ORDER},
        "outputs": {},
        "notes": [
            "Default motion is Grok image_to_video (frame-1 start), not first/last-frame.",
            "Use image_edit + cast master for recurring characters.",
        ],
    }


def load_manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST_NAME
    if not path.is_file():
        raise FilmError(f"No manifest at {path}; run init first")
    return read_json(path)


def director_notes_path(root: Path) -> Path:
    return root / DIRECTOR_NOTES_NAME


def load_director_notes(root: Path) -> dict[str, Any]:
    path = director_notes_path(root)
    if not path.is_file():
        return empty_director_notes()
    data = read_json(path)
    if not isinstance(data, dict):
        return empty_director_notes()
    return data


def save_director_notes(root: Path, notes: dict[str, Any]) -> Path:
    path = director_notes_path(root)
    write_json(path, notes)
    return path


def save_manifest(root: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at"] = utc_now()
    write_json(root / MANIFEST_NAME, manifest)
