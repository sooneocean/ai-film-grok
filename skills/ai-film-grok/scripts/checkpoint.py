"""Hash-bound shot checkpoints for resumable local rendering."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from util import utc_now, write_json

CHECKPOINT_SCHEMA_VERSION = 1
CHECKPOINT_RELATIVE = Path("receipts/checkpoints/final-render.json")


class CheckpointManager:
    """Persist resumable shot work without treating it as delivery evidence."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.path = self.root / CHECKPOINT_RELATIVE
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"schema_version": CHECKPOINT_SCHEMA_VERSION, "shots": {}}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema_version": CHECKPOINT_SCHEMA_VERSION, "shots": {}}
        if not isinstance(raw, dict) or raw.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
            return {"schema_version": CHECKPOINT_SCHEMA_VERSION, "shots": {}}
        shots = raw.get("shots")
        return {**raw, "shots": shots if isinstance(shots, dict) else {}}

    @staticmethod
    def signature(
        clip: Path | str,
        *,
        target: float,
        width: int,
        height: int,
        fps: int,
        lipsync: str,
        in_point_sec: float | None = None,
        out_point_sec: float | None = None,
        contract: dict[str, Any] | None = None,
    ) -> str:
        source = Path(clip).expanduser().resolve()
        stat = source.stat()
        payload = {
            "clip": str(source),
            "device": stat.st_dev,
            "inode": stat.st_ino,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "target": round(float(target), 6),
            "width": int(width),
            "height": int(height),
            "fps": int(fps),
            "lipsync": str(lipsync),
            "in_point_sec": in_point_sec,
            "out_point_sec": out_point_sec,
            "contract": contract or {},
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def get(self, shot_id: str, signature: str) -> dict[str, Any] | None:
        record = self.data["shots"].get(str(shot_id))
        if not isinstance(record, dict) or record.get("signature") != signature:
            return None
        output = Path(str(record.get("output") or ""))
        if not output.is_file() or output.stat().st_size <= 0:
            return None
        return record

    def mark_done(
        self, shot_id: str, *, signature: str, output: Path, metadata: dict[str, Any]
    ) -> None:
        self.data["shots"][str(shot_id)] = {
            "shot_id": str(shot_id),
            "signature": signature,
            "output": str(output),
            "metadata": metadata,
            "completed_at": utc_now(),
        }
        self._write()

    def clear(self) -> None:
        self.data = {"schema_version": CHECKPOINT_SCHEMA_VERSION, "shots": {}}
        if self.path.exists():
            self.path.unlink()

    def _write(self) -> None:
        write_json(self.path, self.data)
