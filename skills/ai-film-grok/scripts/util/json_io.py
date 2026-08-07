"""Strict JSON I/O — thin facade over ``util`` for legacy imports.

Prefer::

    from util import read_json, require_json, write_json

``read_json`` here is **strict** (raises FilmError) for backward compatibility
with early util.json_io callers; package-level ``util.read_json`` stays soft.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util.security_policy import atomic_write_text
from util import require_json, write_json
from util.errors import FilmError  # noqa: F401 — re-export


def read_json(path: Path) -> dict[str, Any]:
    """Strict read (legacy name on this module)."""
    return require_json(path)


__all__ = ["FilmError", "atomic_write_text", "read_json", "write_json"]
