"""Studio registry: scan a studio directory for film roots, summarize each
film's production progress, and merge released films from the video-library
catalog.

Pure and testable — no web framework, no global state. The review-ui server
and the director's 总控台 (command center) both build on this module.

Studio layout (a "studio" is just a directory containing film-root subdirs):

    studio/
      film-a/            <- a film root (has manifest.json)
        manifest.json
        clips/  prompts/  receipts/  ...
      film-b/
        manifest.json
        ...

Released (published) films live separately in ``video-library/catalog.json``
under the ``aifilm-video-library-v1`` schema (``assets`` key) — metadata only,
media is not versioned.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from core.constants import MANIFEST_NAME
from core.film_io import load_manifest
from util import require_json

# Clip statuses that mean "work has started / is in flight" (not a blank draft).
PRODUCING_STATES = frozenset(
    {
        "generating",
        "rendering",
        "reviewing",
        "pending",
        "needs_changes",
        "reshoot",
        "failed",
    }
)

# Default released-films catalog (video-library/catalog.json at the git root).
# studio.py lives at <root>/skills/ai-film-grok/scripts/studio.py, so four
# parents up is the git root.
DEFAULT_CATALOG = Path(__file__).resolve().parents[3] / "video-library" / "catalog.json"


def _mtime_iso(path: Path) -> str:
    """Return the file's mtime as an ISO-8601 UTC string, or '' if unreadable."""
    try:
        ts = path.stat().st_mtime
    except OSError:
        return ""
    return datetime.datetime.fromtimestamp(ts, tz=datetime.UTC).isoformat()


def is_film_root(path: Path) -> bool:
    """A film root is a directory that contains a manifest.json."""
    path = Path(path)
    return path.is_dir() and (path / MANIFEST_NAME).is_file()


def discover_films(studio_dir: Path) -> list[Path]:
    """Return film-root subdirectories of ``studio_dir`` (sorted by name)."""
    studio_dir = Path(studio_dir)
    if not studio_dir.is_dir():
        return []
    return sorted(
        (child for child in studio_dir.iterdir() if is_film_root(child)),
        key=lambda p: p.name,
    )


def film_id(root: Path) -> str:
    return Path(root).name


def _genre_of(manifest: dict[str, Any]) -> str:
    return manifest.get("genre") or manifest.get("theme") or ""


def summarize_film(root: Path) -> dict[str, Any]:
    """Compute a compact progress summary for one film root.

    Returns a dict with: id, title, theme, genre, aspect_ratio, status
    (draft|producing|released), progress (0-100), clips_total, clips_approved,
    gates_total, gates_passed, style_locked, last_updated, root.
    """
    root = Path(root)
    manifest = load_manifest(root)
    clips = manifest.get("clips", {}) or {}
    gates = manifest.get("gates", {}) or {}

    clips_total = len(clips)
    clips_approved = sum(
        1 for c in clips.values() if isinstance(c, dict) and c.get("status") == "approved"
    )
    gates_total = len(gates)
    gates_passed = sum(1 for v in gates.values() if v)

    clip_progress = (clips_approved / clips_total) if clips_total else 0.0
    gate_progress = (gates_passed / gates_total) if gates_total else 0.0
    progress = round(100 * (0.6 * clip_progress + 0.4 * gate_progress))

    if manifest.get("released"):
        status = "released"
    elif clips_approved > 0 or any(
        isinstance(c, dict) and c.get("status") in PRODUCING_STATES for c in clips.values()
    ):
        status = "producing"
    else:
        status = "draft"

    last_updated = manifest.get("updated_at") or _mtime_iso(root / MANIFEST_NAME)

    return {
        "id": film_id(root),
        "title": manifest.get("title", root.name),
        "theme": manifest.get("theme", ""),
        "genre": _genre_of(manifest),
        "aspect_ratio": manifest.get("aspect_ratio", ""),
        "status": status,
        "progress": progress,
        "clips_total": clips_total,
        "clips_approved": clips_approved,
        "gates_total": gates_total,
        "gates_passed": gates_passed,
        "style_locked": bool(manifest.get("style_locked", False)),
        "last_updated": last_updated,
        "root": str(root),
    }


def load_released(catalog_path: Path | None = None) -> list[dict[str, Any]]:
    """Read released films from the video-library catalog (``assets`` key).

    Returns [] when the catalog is missing or has no assets. Never raises on a
    missing/empty catalog — releasing metadata is best-effort.
    """
    catalog_path = Path(catalog_path) if catalog_path else DEFAULT_CATALOG
    if not catalog_path.is_file():
        return []
    data = require_json(catalog_path)
    if not isinstance(data, dict):
        return []
    assets = data.get("assets", {}) or {}
    out: list[dict[str, Any]] = []
    for aid, a in assets.items():
        if not isinstance(a, dict):
            continue
        out.append(
            {
                "id": aid,
                "title": a.get("title", aid),
                "genre": a.get("genre") or a.get("theme", ""),
                "theme": a.get("theme", ""),
                "status": "released",
                "progress": 100,
                "released_at": a.get("released_at") or data.get("updated_at"),
                "duration_sec": a.get("duration_sec"),
                "root": a.get("root", ""),
            }
        )
    return out


def build_studio(
    studio_dir: Path,
    catalog_path: Path | None = None,
    active_id: str | None = None,
) -> dict[str, Any]:
    """Build the full studio summary: films grid + released + category breakdown.

    ``active_id`` marks which film is currently the active workbench film.
    Films are sorted most-recently-updated first for the director's view.
    """
    studio_dir = Path(studio_dir)
    films: list[dict[str, Any]] = []
    broken: list[str] = []
    for root in discover_films(studio_dir):
        try:
            films.append(summarize_film(root))
        except Exception:
            broken.append(root.name)

    # most-recent first
    films.sort(key=lambda f: (f.get("last_updated") or ""), reverse=True)

    released = load_released(catalog_path)

    categories: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for f in films + released:
        g = f.get("genre") or f.get("theme") or "未分类"
        categories[g] = categories.get(g, 0) + 1
        s = f.get("status", "draft")
        status_counts[s] = status_counts.get(s, 0) + 1

    if active_id is None and films:
        active_id = films[0]["id"]

    return {
        "studio_dir": str(studio_dir),
        "studio_mode": True,
        "film_count": len(films),
        "released_count": len(released),
        "films": films,
        "released": released,
        "categories": categories,
        "status_counts": status_counts,
        "active_film_id": active_id,
        "broken_film_roots": broken,
    }


def single_film_view(active_root: Path) -> dict[str, Any]:
    """Studio-shaped payload for single-root (non-studio) serve mode.

    Presents the one film as the only entry; useful so the 总控台 UI works in
    both modes without branching.
    """
    active_root = Path(active_root)
    summary = summarize_film(active_root)
    status = summary["status"]
    return {
        "studio_dir": None,
        "studio_mode": False,
        "film_count": 1,
        "released_count": 0,
        "films": [summary],
        "released": [],
        "categories": {summary["genre"] or "未分类": 1} if summary["genre"] else {},
        "status_counts": {status: 1},
        "active_film_id": summary["id"],
        "broken_film_roots": [],
    }
