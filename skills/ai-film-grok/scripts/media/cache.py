"""Small content-addressed disk cache for deterministic local pipeline work."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class ContentCache:
    """Store immutable cache entries below ``<root>/cache``.

    Keys are restricted to SHA-256 hex digests so callers cannot escape the
    cache directory. Writes are atomic; a failed producer never publishes a
    partial cache entry.
    """

    def __init__(self, root: Path | str, *, namespace: str = "default") -> None:
        base = Path(root).expanduser().resolve()
        if not namespace or "/" in namespace or "\\" in namespace or namespace in {".", ".."}:
            raise ValueError("cache namespace must be a single safe path component")
        self.root = base / "cache" / namespace

    @staticmethod
    def key(data: bytes | str) -> str:
        payload = data.encode("utf-8") if isinstance(data, str) else data
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def contract_key(
        *,
        input_hash: str,
        provider: str,
        model: str,
        parameters: dict[str, Any] | None = None,
        version: str = "1",
    ) -> str:
        """Build a stable cache key from the complete generation contract."""
        payload = {
            "input_hash": str(input_hash),
            "provider": str(provider),
            "model": str(model),
            "parameters": parameters or {},
            "version": str(version),
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return ContentCache.key(encoded)

    @staticmethod
    def file_fingerprint(path: Path | str) -> str:
        source = Path(path).expanduser().resolve()
        stat = source.stat()
        return ContentCache.key(
            json.dumps(
                {
                    "path": str(source),
                    "device": stat.st_dev,
                    "inode": stat.st_ino,
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    def _path(self, key: str) -> Path:
        if len(key) != 64 or any(c not in "0123456789abcdef" for c in key.lower()):
            raise ValueError("cache key must be a SHA-256 hex digest")
        return self.root / f"{key.lower()}.json"

    def get(self, key: str) -> bytes | None:
        path = self._path(key)
        try:
            return path.read_bytes() if path.is_file() else None
        except OSError:
            return None

    def put(self, key: str, data: bytes) -> Path:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "wb", dir=target.parent, prefix=f".{target.name}.", delete=False
        ) as handle:
            handle.write(data)
            temporary = Path(handle.name)
        os.replace(temporary, target)
        return target

    def get_json(self, key: str) -> dict[str, Any] | None:
        raw = self.get(key)
        if raw is None:
            return None
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def put_json(self, key: str, value: dict[str, Any]) -> Path:
        return self.put(
            key,
            (
                json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode("utf-8"),
        )
