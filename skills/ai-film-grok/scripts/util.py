"""Shared I/O and general-purpose utilities for the ai-film-grok pipeline."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any] | None:
    """Read and parse a JSON file.

    Returns the parsed dict on success, or *None* if the file is missing,
    unreadable, or contains invalid JSON.  Callers that expect a default
    empty dict should write ``read_json(p) or {}``.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def write_json(path: Path, data: Any) -> None:
    """Serialise *data* as pretty-printed JSON and write to *path*.

    Creates parent directories automatically.  Uses ``ensure_ascii=False``
    so Unicode characters are written verbatim.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def ensure_dir(path: Path) -> Path:
    """Like ``mkdir -p`` — create *path* if missing, no-op if exists."""
    path.mkdir(parents=True, exist_ok=True)
    return path
