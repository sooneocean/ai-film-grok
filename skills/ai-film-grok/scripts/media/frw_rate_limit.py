"""Shared FRW platform rate limits (image ≥30s, video ≥5min).

Aligned with ai-film-frw ``utils.wait_frw_rate_limit`` so concurrent shells and
both skills honor the same durable ceiling under::

    ~/.hermes/cache/ai-film-frw-frw-rate.json
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

HOME = Path.home()
IMAGE_MIN_INTERVAL_S = 30.0
VIDEO_MIN_INTERVAL_S = 300.0  # 5 minutes
_DEFAULT_RATE_STATE = HOME / ".hermes" / "cache" / "ai-film-frw-frw-rate.json"


def _rate_state_path() -> Path:
    override = os.environ.get("AIFILM_FRW_RATE_STATE", "").strip()
    if override:
        return Path(override).expanduser()
    return _DEFAULT_RATE_STATE


# Back-compat alias (resolved at call time via helpers when possible)
RATE_STATE_PATH = _DEFAULT_RATE_STATE

_IMAGE_CMDS = frozenset(
    {
        "text2image",
        "img2image",
        "face-swap",
        "pose-control",
    }
)
_VIDEO_CMDS = frozenset(
    {
        "first-last-frame",
        "img2video",
        "img2video-audio",
        "text2video",
        "compose-video",
        "video-continue",
        "merge-video",
        "newvideo",  # frwclaw catalog bulk I2V
    }
)


class SubmitBudget:
    """Cap FRW image/video submits per invocation for unit orchestration."""

    def __init__(self, max_submits: int | None = None) -> None:
        self.max_submits = max_submits
        self.used = 0

    def take(self) -> None:
        if self.max_submits is not None and self.used >= self.max_submits:
            raise RuntimeError(
                f"Submit budget exhausted ({self.used}/{self.max_submits}). "
                "Re-run for the next unit (image ≥30s gap)."
            )
        self.used += 1


def classify_frw_op(args: list[str]) -> str | None:
    """Return 'image' | 'video' | None for rate-limited submit ops (not queries)."""
    if not args:
        return None
    op = str(args[0]).strip().lower()
    if op.endswith("-query") or op in {
        "upload",
        "batch-upload",
        "archive-upload",
        "text2text",
        "upload-probe",
        "upload-canary",
        "canary",
        "help",
        "ab",
        "capabilities",
    }:
        return None
    if op in _IMAGE_CMDS:
        return "image"
    if op in _VIDEO_CMDS:
        return "video"
    return None


def _load_rate_state(path: Path | None = None) -> dict[str, float]:
    path = path or _rate_state_path()
    out: dict[str, float] = {"image": 0.0, "video": 0.0}
    if not path.is_file():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return out
    if not isinstance(data, dict):
        return out
    for key in ("image", "video"):
        try:
            out[key] = float(data.get(key) or 0.0)
        except (TypeError, ValueError):
            out[key] = 0.0
    return out


def _save_rate_state(state: dict[str, float], path: Path | None = None) -> None:
    path = path or _rate_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    payload = {
        "schema_version": 1,
        "image": float(state.get("image") or 0.0),
        "video": float(state.get("video") or 0.0),
        "updated_at": time.time(),
    }
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def peek_frw_rate_wait(
    kind: str,
    *,
    now: float | None = None,
    state_path: Path | None = None,
) -> float:
    """Seconds until *kind* may submit, without mutating rate state."""
    if kind not in ("image", "video"):
        return 0.0
    min_gap = IMAGE_MIN_INTERVAL_S if kind == "image" else VIDEO_MIN_INTERVAL_S
    t0 = time.time() if now is None else float(now)
    last = float(_load_rate_state(state_path or _rate_state_path()).get(kind) or 0.0)
    return max(0.0, min_gap - (t0 - last))


def frw_rate_snapshot(
    *,
    now: float | None = None,
    state_path: Path | None = None,
) -> dict[str, Any]:
    """Observation-only rate window for orchestrators / still-challenge plan."""
    t0 = time.time() if now is None else float(now)
    path = state_path or _rate_state_path()
    state = _load_rate_state(path)
    image_wait = peek_frw_rate_wait("image", now=t0, state_path=path)
    video_wait = peek_frw_rate_wait("video", now=t0, state_path=path)
    return {
        "image_min_interval_s": IMAGE_MIN_INTERVAL_S,
        "video_min_interval_s": VIDEO_MIN_INTERVAL_S,
        "image_last_submit_ts": float(state.get("image") or 0.0),
        "video_last_submit_ts": float(state.get("video") or 0.0),
        "image_wait_s": round(image_wait, 1),
        "video_wait_s": round(video_wait, 1),
        "image_ready": image_wait <= 0.05,
        "video_ready": video_wait <= 0.05,
        "state_path": str(path),
        "as_of_ts": t0,
    }


def wait_frw_rate_limit(
    kind: str,
    *,
    now: float | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
    state_path: Path | None = None,
    log: Callable[[str], None] | None = None,
) -> float:
    """Block until the shared FRW rate window allows *kind* ('image'|'video').

    Returns seconds actually slept (0 if no wait). Persists last-submit timestamps
    so separate processes honor the same ceiling.
    """
    if kind not in ("image", "video"):
        return 0.0
    if os.environ.get("AIFILM_FRW_RATE_LIMIT", "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return 0.0
    min_gap = IMAGE_MIN_INTERVAL_S if kind == "image" else VIDEO_MIN_INTERVAL_S
    path = state_path or _rate_state_path()
    lock_path = path.with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd: int | None = None
    slept = 0.0
    log_fn = log or (lambda msg: print(msg, flush=True))
    try:
        class _LockBusy(RuntimeError):
            """Internal: rate-state lock held — util.retry only."""

        def _try_open_lock() -> int:
            try:
                return os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError as exc:
                raise _LockBusy("frw rate lock busy") from exc

        from util.retry import retry_call

        # 120s / 0.05s ≈ 2400 attempts at constant delay (backoff=1).
        try:
            lock_fd = retry_call(
                _try_open_lock,
                attempts=2400,
                delay_sec=0.05,
                backoff=1.0,
                retry_on=(_LockBusy,),
                sleep=sleep_fn,
            )
        except _LockBusy:
            lock_fd = None
        t0 = time.time() if now is None else float(now)
        state = _load_rate_state(path)
        last = float(state.get(kind) or 0.0)
        wait_s = min_gap - (t0 - last)
        if wait_s > 0.05:
            log_fn(f"[frw-rate] {kind}: wait {wait_s:.1f}s (min gap {min_gap:.0f}s)")
            sleep_fn(wait_s)
            slept = wait_s
            t0 = time.time() if now is None else (float(now) + wait_s)
        state[kind] = t0
        _save_rate_state(state, path)
        return slept
    finally:
        if lock_fd is not None:
            with contextlib.suppress(OSError):
                os.close(lock_fd)
            with contextlib.suppress(OSError):
                lock_path.unlink(missing_ok=True)
