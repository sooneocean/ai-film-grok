"""Shared, non-interactive FFmpeg/ffprobe helpers for media evidence."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from security_policy import minimal_subprocess_env

DEFAULT_PROBE_TIMEOUT = 60
DEFAULT_DECODE_TIMEOUT = 180


class MediaProbeError(RuntimeError):
    """A media command could not produce trustworthy evidence."""


def _tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise MediaProbeError(f"{name} not found on PATH")
    return path


def run_media_command(
    command: list[str], *, timeout: float, check: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run FFmpeg-family commands without allowing stdin to block a pipeline."""
    if not command:
        raise MediaProbeError("media command is empty")
    executable = Path(command[0]).name
    if executable not in {"ffmpeg", "ffprobe"}:
        raise MediaProbeError(f"unsupported media executable: {executable}")
    argv = list(command)
    if "-nostdin" not in argv:
        insert_at = 1
        argv.insert(insert_at, "-nostdin")
    try:
        process = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            env=minimal_subprocess_env(),
        )
    except FileNotFoundError as exc:
        raise MediaProbeError(f"{executable} not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaProbeError(f"{executable} timed out after {timeout:g}s") from exc
    except subprocess.SubprocessError as exc:
        raise MediaProbeError(f"{executable} could not start: {exc}") from exc
    if check and process.returncode != 0:
        detail = (process.stderr or process.stdout or "no diagnostic output").strip()
        raise MediaProbeError(f"{executable} failed (rc={process.returncode}): {detail[-1000:]}")
    return process


def probe_media(
    path: Path | str,
    *,
    count_frames: bool = False,
    timeout: float = DEFAULT_PROBE_TIMEOUT,
) -> dict[str, Any]:
    """Read stable stream/format metadata from one media file."""
    source = Path(path).expanduser().resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise MediaProbeError(f"media file is missing or empty: {source}")
    entries = "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,duration"
    if count_frames:
        entries = "format=duration:stream=codec_type,codec_name,width,height,nb_read_frames,avg_frame_rate,duration"
    process = run_media_command(
        [
            _tool("ffprobe"),
            "-v",
            "error",
            "-show_entries",
            entries,
            "-of",
            "json",
            str(source),
        ],
        timeout=timeout,
        check=True,
    )
    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise MediaProbeError(f"ffprobe returned invalid JSON for {source}") from exc
    if not isinstance(report, dict):
        raise MediaProbeError(f"ffprobe returned a non-object report for {source}")
    report["path"] = str(source)
    return report


def verify_full_decode(path: Path | str, *, timeout: float = DEFAULT_DECODE_TIMEOUT) -> None:
    """Decode the complete video without writing an output file."""
    source = Path(path).expanduser().resolve()
    run_media_command(
        [_tool("ffmpeg"), "-v", "error", "-xerror", "-i", str(source), "-f", "null", "-"],
        timeout=timeout,
        check=True,
    )
