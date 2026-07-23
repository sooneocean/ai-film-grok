"""Shared, non-interactive FFmpeg/ffprobe helpers for media evidence."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
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
    if executable == "ffmpeg" and "-nostdin" not in argv:
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
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "no diagnostic output").strip()
        raise MediaProbeError(
            f"{executable} failed (rc={exc.returncode}): {detail[-1000:]}"
        ) from exc
    except subprocess.SubprocessError as exc:
        raise MediaProbeError(f"{executable} could not start: {exc}") from exc
    if check and process.returncode != 0:
        detail = (process.stderr or process.stdout or "no diagnostic output").strip()
        raise MediaProbeError(f"{executable} failed (rc={process.returncode}): {detail[-1000:]}")
    return process


def run_media_to_output(
    command: list[str],
    output: Path | str,
    *,
    timeout: float = DEFAULT_DECODE_TIMEOUT,
    min_bytes: int = 100,
    validate: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a media writer against a sibling temp file, then publish atomically.

    A failed encode must never replace a previously registered deliverable.
    ``output`` is replaced only after the process succeeds, the file is non-empty,
    and (by default) ffprobe can read it.
    """
    target = Path(output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.stem}.{uuid.uuid4().hex}{target.suffix}")
    argv = list(command)
    target_text = str(output)
    resolved_text = str(target)
    replaced = False
    for index, value in enumerate(argv):
        if value in {target_text, resolved_text}:
            argv[index] = str(temp)
            replaced = True
    if not replaced:
        raise MediaProbeError(f"media output is not present in command: {target}")
    try:
        process = run_media_command(argv, timeout=timeout, check=True)
        if not temp.is_file() or temp.stat().st_size < min_bytes:
            raise MediaProbeError(f"media command produced an empty or undersized output: {temp}")
        if validate:
            probe_media(temp, timeout=min(DEFAULT_PROBE_TIMEOUT, timeout))
        os.replace(temp, target)
        return process
    except MediaProbeError:
        raise
    finally:
        temp.unlink(missing_ok=True)


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
