"""Final render stage heartbeat — detects hung long renders (v2.40)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from util import write_json

HEARTBEAT_NAME = "final-heartbeat.json"


def write_final_heartbeat(
    root: Path | str,
    *,
    stage: str,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    root_p = Path(root).expanduser().resolve()
    rec_dir = root_p / "receipts"
    rec_dir.mkdir(parents=True, exist_ok=True)
    path = rec_dir / HEARTBEAT_NAME
    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "final-heartbeat",
        "stage": stage,
        "detail": detail,
        "pid": os.getpid(),
        "unix": time.time(),
    }
    if extra:
        payload["extra"] = extra
    write_json(path, payload)
    return path


def default_ffmpeg_timeout_sec() -> int:
    raw = os.environ.get("AIFILM_FINAL_FFMPEG_TIMEOUT_SEC", "").strip()
    if raw:
        try:
            return max(60, int(raw))
        except ValueError:
            pass
    return 900  # 15 min per heavy ffmpeg stage
