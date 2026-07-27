#!/usr/bin/env python3
"""Serialize expensive local release checks used by the pre-push hook."""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class ReleaseGateError(RuntimeError):
    """Describe a local condition that prevents a release check from starting."""


def git_internal_path(root: Path, name: str) -> Path:
    """Resolve a local Git control file for normal and linked worktrees."""
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "rev-parse",
            "--git-path",
            name,
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


def release_lock_path(root: Path) -> Path:
    """Resolve the advisory lock through Git for linked-worktree support."""
    return git_internal_path(root, "ai-film-grok-release-gate.lock")


def release_success_receipt_path(root: Path) -> Path:
    """Keep successful-gate state local to Git instead of tracking it in the worktree."""
    return git_internal_path(root, "ai-film-grok-release-gate-success.json")


def current_clean_head(root: Path) -> str:
    """Fail closed if tracked edits would make a worktree test diverge from the pushed commit."""
    for args in (("diff", "--quiet"), ("diff", "--cached", "--quiet")):
        result = subprocess.run(["git", "-C", str(root), *args], check=False)
        if result.returncode == 1:
            raise ReleaseGateError(
                "tracked worktree changes are present; commit or stash them before pushing"
            )
        if result.returncode:
            raise ReleaseGateError(
                f"cannot inspect Git worktree state: {' '.join(args)}"
            )
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    head = result.stdout.strip()
    if result.returncode or not head:
        raise ReleaseGateError("cannot resolve Git HEAD for release gate")
    return head


def successful_receipt_matches(path: Path, head: str) -> bool:
    """Reuse only a valid local receipt for the exact clean commit being pushed."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(data, dict)
        and data.get("head") == head
        and data.get("status") == "passed"
    )


def write_success_receipt(path: Path, head: str) -> None:
    """Atomically record a completed gate while its exclusive lock is still held."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"head": head, "status": "passed"}, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


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
    """Run or safely reuse the full pre-push validation for one clean Git HEAD."""
    root = root.expanduser().resolve()
    lock_path = release_lock_path(root)
    receipt_path = release_success_receipt_path(root)
    with exclusive_release_lock(lock_path, timeout_sec=timeout_sec):
        head = current_clean_head(root)
        if successful_receipt_matches(receipt_path, head):
            print(f"[release] reusing successful gate for {head[:12]}")
            return 0
        sync = subprocess.run(
            [sys.executable, str(root / "scripts" / "sync_project_docs.py"), "--check"],
            cwd=root,
            check=False,
        )
        if sync.returncode:
            return sync.returncode
        release = subprocess.run(["make", "release-check"], cwd=root, check=False)
        if release.returncode == 0:
            write_success_receipt(receipt_path, head)
        return release.returncode


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
