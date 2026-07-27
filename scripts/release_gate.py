#!/usr/bin/env python3
"""Serialize expensive local release checks used by the pre-push hook."""

from __future__ import annotations

import argparse
import errno
import fcntl
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class ReleaseGateError(RuntimeError):
    """Describe a local condition that prevents a release check from starting."""


def release_lock_path(root: Path) -> Path:
    """Resolve the lock through Git so linked worktrees do not treat `.git` as a directory."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "rev-parse",
            "--git-path",
            "ai-film-grok-release-gate.lock",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    raw_path = result.stdout.strip()
    if result.returncode or not raw_path:
        detail = result.stderr.strip() or "git did not return a lock path"
        raise ReleaseGateError(f"cannot resolve release-gate lock: {detail}")
    lock_path = Path(raw_path)
    return lock_path if lock_path.is_absolute() else root / lock_path


@contextmanager
def exclusive_release_lock(path: Path, *, timeout_sec: float) -> Iterator[None]:
    """Hold a process-scoped advisory lock, waiting only up to the stated timeout."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        deadline = time.monotonic() + timeout_sec
        announced = False
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"release gate remained busy for {timeout_sec:.0f}s: {path}"
                    ) from exc
                if not announced:
                    print(
                        "[release] another check is running; waiting for its gate",
                        file=sys.stderr,
                    )
                    announced = True
                time.sleep(0.25)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def run_release_gate(root: Path, *, timeout_sec: float = 900) -> int:
    """Run both pre-push validations under one repository-local lock."""
    root = root.expanduser().resolve()
    lock_path = release_lock_path(root)
    with exclusive_release_lock(lock_path, timeout_sec=timeout_sec):
        sync = subprocess.run(
            [sys.executable, str(root / "scripts" / "sync_project_docs.py"), "--check"],
            cwd=root,
            check=False,
        )
        if sync.returncode:
            return sync.returncode
        return subprocess.run(
            ["make", "release-check"], cwd=root, check=False
        ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-sec", type=float, default=900)
    args = parser.parse_args()
    try:
        return run_release_gate(
            Path(__file__).resolve().parents[1], timeout_sec=args.timeout_sec
        )
    except (ReleaseGateError, TimeoutError) as exc:
        print(f"pre-push blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
