"""Final render stage heartbeat — detects hung long renders (v2.40+)."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from util import write_json

HEARTBEAT_NAME = "final-heartbeat.json"
TIMEOUT_RECEIPT = "final-timeout.json"

# Ordered stages for hang diagnosis (receipts/final-heartbeat.json.stage)
STAGES = (
    "start",
    "tts",
    "stretch",
    "video_concat",
    "audio_mix",
    "encode",
    "subs",
    "qa",
    "done",
)


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


def write_final_timeout_receipt(
    root: Path | str,
    *,
    stage: str,
    timeout_sec: float | int | None,
    error: str,
) -> Path:
    """Honest hang receipt — never fake a green final."""
    root_p = Path(root).expanduser().resolve()
    rec_dir = root_p / "receipts"
    rec_dir.mkdir(parents=True, exist_ok=True)
    path = rec_dir / TIMEOUT_RECEIPT
    payload = {
        "schema_version": 1,
        "kind": "final-timeout",
        "ok": False,
        "stage": stage,
        "timeout_sec": timeout_sec,
        "error": error[:2000],
        "pid": os.getpid(),
        "unix": time.time(),
        "next_cmd": (
            f'aifilm final --root "{root_p}" --lipsync off --music-mood rnb '
            f"--tts-backend edge  # last stage={stage}; raise AIFILM_FFMPEG_TIMEOUT "
            f"or AIFILM_FINAL_FFMPEG_TIMEOUT_SEC; check receipts/{HEARTBEAT_NAME}"
        ),
    }
    write_json(path, payload)
    write_final_heartbeat(root_p, stage=f"timeout:{stage}", detail=error[:200])
    return path


def default_ffmpeg_timeout_sec() -> int:
    """Prefer final-specific env, then shared AIFILM_FFMPEG_TIMEOUT, else 900s."""
    for key in ("AIFILM_FINAL_FFMPEG_TIMEOUT_SEC", "AIFILM_FFMPEG_TIMEOUT"):
        raw = os.environ.get(key, "").strip()
        if raw:
            try:
                return max(60, int(float(raw)))
            except ValueError:
                continue
    return 900


def apply_final_ffmpeg_timeout_env() -> int:
    """Ensure ffmpeg wrappers see a bounded timeout for this final process."""
    sec = default_ffmpeg_timeout_sec()
    # run_ffmpeg reads AIFILM_FFMPEG_TIMEOUT; keep FINAL in sync for operators.
    os.environ.setdefault("AIFILM_FFMPEG_TIMEOUT", str(sec))
    os.environ.setdefault("AIFILM_FINAL_FFMPEG_TIMEOUT_SEC", str(sec))
    return sec
