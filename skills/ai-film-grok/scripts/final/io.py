"""Final JSON I/O (closeout)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    from util import require_json_fnv
    return require_json_fnv(path)
