"""Final JSON I/O (closeout) — C5.3 hard-compat facade over util (no local parser)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from util import require_json_fnv


def read_json(path: Path) -> dict[str, Any]:
    """Strict read: FileNotFoundError / ValueError (legacy final path)."""
    return require_json_fnv(path)
