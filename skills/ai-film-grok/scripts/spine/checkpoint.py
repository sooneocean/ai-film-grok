"""Hash-bound shot checkpoints for resumable local rendering."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from media_probe import probe_media, verify_full_decode
from util import sha256_file, utc_now, write_json

CHECKPOINT_SCHEMA_VERSION = 2
CHECKPOINT_RELATIVE = Path("receipts/checkpoints/final-render.json")


class CheckpointManager:
    """Persist resumable shot work without treating it as delivery evidence."""

    def __init__(self, root: Path | str, *, preserve_corrupt: bool = True) -> None:
        self.root = Path(root).expanduser().resolve()
        self.path = self.root / CHECKPOINT_RELATIVE
        self.preserve_corrupt = bool(preserve_corrupt)
        self.corrupt_detected = False
        self.corrupt_backup: Path | None = None
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._empty()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.corrupt_detected = True
            if self.preserve_corrupt:
                self._preserve_corrupt()
            return self._empty()
        if not isinstance(raw, dict) or raw.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
            self.corrupt_detected = True
            if self.preserve_corrupt:
                self._preserve_corrupt()
            return self._empty()
        shots = raw.get("shots")
        stages = raw.get("stages")
        return {
            **raw,
            "shots": shots if isinstance(shots, dict) else {},
            "stages": stages if isinstance(stages, dict) else {},
        }

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {"schema_version": CHECKPOINT_SCHEMA_VERSION, "shots": {}, "stages": {}}

    def _preserve_corrupt(self) -> None:
        if not self.path.is_file():
            return
        stamp = utc_now().replace(":", "").replace("+", "_")
        backup = self.path.with_name(f"{self.path.name}.corrupt.{stamp}")
        try:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.path, backup)
        except OSError:
            return
        self.corrupt_backup = backup

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
        if not self._record_is_current(record):
            return None
        return record

    def mark_done(
        self, shot_id: str, *, signature: str, output: Path, metadata: dict[str, Any]
    ) -> None:
        evidence = _media_evidence(output)
        self.data["shots"][str(shot_id)] = {
            "shot_id": str(shot_id),
            "signature": signature,
            "output": str(output),
            "evidence": evidence,
            "metadata": metadata,
            "completed_at": utc_now(),
        }
        self._write()

    def get_stage(self, unit_id: str, stage_id: str, signature: str) -> dict[str, Any] | None:
        unit = self.data["stages"].get(str(unit_id))
        record = unit.get(str(stage_id)) if isinstance(unit, dict) else None
        if not isinstance(record, dict) or record.get("signature") != signature:
            return None
        if not self._record_is_current(record):
            return None
        return record

    def mark_stage_done(
        self,
        unit_id: str,
        stage_id: str,
        *,
        signature: str,
        output: Path,
        depends_on: list[str],
        metadata: dict[str, Any],
    ) -> None:
        unit = self.data["stages"].setdefault(str(unit_id), {})
        unit[str(stage_id)] = {
            "unit_id": str(unit_id),
            "stage_id": str(stage_id),
            "signature": signature,
            "output": str(output),
            "depends_on": [str(item) for item in depends_on],
            "evidence": _media_evidence(output),
            "metadata": metadata,
            "completed_at": utc_now(),
        }
        self._write()

    @staticmethod
    def _record_is_current(record: dict[str, Any]) -> bool:
        output = Path(str(record.get("output") or ""))
        evidence = record.get("evidence")
        if not output.is_file() or output.stat().st_size <= 0 or not isinstance(evidence, dict):
            return False
        expected = str(evidence.get("sha256") or "")
        if not expected or sha256_file(output) != expected:
            return False
        try:
            current = _media_evidence(output)
        except (OSError, ValueError, RuntimeError):
            return False
        return bool(
            current.get("full_decode") is True
            and current.get("sha256") == expected
            and current.get("bytes") == evidence.get("bytes")
        )

    def clear(self) -> None:
        self.data = self._empty()
        if self.path.exists():
            self.path.unlink()

    def _write(self) -> None:
        write_json(self.path, self.data)


def _media_evidence(path: Path) -> dict[str, Any]:
    output = Path(path).expanduser().resolve()
    report = probe_media(output, count_frames=True)
    verify_full_decode(output)
    streams = list(report.get("streams") or [])
    video = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if not isinstance(video, dict):
        raise ValueError(f"checkpoint output has no video stream: {output}")
    duration_raw = (report.get("format") or {}).get("duration") or video.get("duration")
    duration = float(duration_raw)
    if duration <= 0:
        raise ValueError(f"checkpoint output has invalid duration: {output}")
    return {
        "sha256": sha256_file(output),
        "bytes": output.stat().st_size,
        "duration_sec": duration,
        "video": {
            "codec_name": video.get("codec_name"),
            "width": video.get("width"),
            "height": video.get("height"),
            "avg_frame_rate": video.get("avg_frame_rate"),
            "nb_read_frames": video.get("nb_read_frames"),
        },
        "audio_streams": sum(
            1
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "audio"
        ),
        "full_decode": True,
    }
