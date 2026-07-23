"""Subprocess wrappers with security-policy minimal env."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def run(
    cmd: list[str],
    *,
    check: bool = True,
    timeout: int | float | None = 60,
) -> subprocess.CompletedProcess[str]:
    from security_policy import minimal_subprocess_env

    return subprocess.run(
        cmd,
        timeout=timeout,
        check=check,
        capture_output=True,
        text=True,
        env=minimal_subprocess_env(),
    )


def run_compose_env(
    cmd: list[str],
    *,
    cwd: Path | str | None = None,
    check: bool = True,
    timeout: int | float | None = 60,
) -> subprocess.CompletedProcess[str]:
    from security_policy import minimal_subprocess_env

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
    )
