"""Shared I/O and general-purpose utilities for the ai-film-grok pipeline."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


def canonical_json_sha256(value: Any) -> str:
    """Hash JSON data with the repository's canonical serialization contract."""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash large media without loading the complete file into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


@contextmanager
def exclusive_file_lock(path: Path) -> Iterator[None]:
    """Serialize optimistic read-check-replace writers for one canonical file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    with lock_path.open("a+", encoding="utf-8") as handle:
        os.chmod(lock_path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def ensure_dir(path: Path) -> Path:
    """Like ``mkdir -p`` — create *path* if missing, no-op if exists."""
    path.mkdir(parents=True, exist_ok=True)
    return path
