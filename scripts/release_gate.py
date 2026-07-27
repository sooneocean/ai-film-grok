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
    lock_path = root / ".git" / "ai-film-grok-release-gate.lock"
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
    except TimeoutError as exc:
        print(f"pre-push blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
