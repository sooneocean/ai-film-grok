"""Strict JSON I/O — thin facade over ``util`` for legacy imports.

Prefer::

    from util import read_json, require_json, write_json

``read_json`` here is **strict** (raises FilmError) for backward compatibility
with early util.json_io callers; package-level ``util.read_json`` stays soft.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import require_json, write_json
from util.errors import FilmError  # noqa: F401 — re-export


def read_json(path: Path) -> dict[str, Any]:
    """Strict read (legacy name on this module)."""
    return require_json(path)


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import os
    import tempfile

    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding=encoding, dir=path.parent, delete=False
        ) as handle:
            handle.write(content)
            temp = Path(handle.name)
        os.replace(temp, path)
        temp = None
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


__all__ = ["FilmError", "atomic_write_text", "read_json", "write_json"]
