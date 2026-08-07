"""Subprocess wrappers with security-policy minimal env."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any


def run(
    cmd: list[str],
    *,
    check: bool = True,
    timeout: int | float | None = 60,
) -> subprocess.CompletedProcess[str]:
    """Canonical subprocess runner. ``timeout=None`` → 60s (C5.5 hang protection)."""
    from util.security_policy import minimal_subprocess_env

    if timeout is None:
        timeout = 60
    return subprocess.run(
        cmd,
        timeout=timeout,
        check=check,
        capture_output=True,
        text=True,
        env=minimal_subprocess_env(),
    )


def run_ffmpeg(
    cmd: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """FFmpeg wrapper: injects ``-nostdin`` and applies ``AIFILM_FFMPEG_TIMEOUT``."""
    from util.security_policy import minimal_subprocess_env

    argv = list(cmd)
    if "-nostdin" not in argv:
        argv.insert(1, "-nostdin")
    try:
        ff_timeout = float(os.environ.get("AIFILM_FFMPEG_TIMEOUT") or 1800)
    except (TypeError, ValueError):
        ff_timeout = 1800.0
    ff_timeout = max(120.0, ff_timeout)
    return subprocess.run(
        argv,
        timeout=ff_timeout,
        check=check,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        env=minimal_subprocess_env(),
    )


def run_compose_env(
    cmd: list[str],
    *,
    cwd: Path | str | None = None,
    check: bool = True,
    timeout: int | float | None = 60,
    stdin: Any | None = None,
) -> subprocess.CompletedProcess[str]:
    """Compose/post subprocess with minimal env.

    ``timeout=None`` → 60s so thin facades cannot disable hang protection (C5.5).
    """
    from util.security_policy import minimal_subprocess_env

    if timeout is None:
        timeout = 60
    env = minimal_subprocess_env()
    for key in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL", "NODE_PATH", "npm_config_cache"):
        if key in os.environ:
            env[key] = os.environ[key]
    if "HOME" in env:
        env.setdefault("npm_config_cache", str(Path(env["HOME"]) / ".npm"))
    return subprocess.run(
        cmd,
        cwd=str(Path(cwd)) if cwd else None,
        check=check,
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
        stdin=stdin,
    )
