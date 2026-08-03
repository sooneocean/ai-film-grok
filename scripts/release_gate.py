#!/usr/bin/env python3
"""Serialize local release checks used by the pre-push hook.

Default mode is **light** (docs currency + doctor core) so agent/human push
is not blocked by a multi-minute full pytest suite. Full gate remains available:

  AIFILM_RELEASE_GATE=full git push

Or: python3 scripts/release_gate.py --mode full
"""

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


def successful_receipt_matches(path: Path, head: str, mode: str) -> bool:
    """Reuse only a valid local receipt for the exact clean commit + mode."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    if data.get("head") != head or data.get("status") != "passed":
        return False
    # Full receipt satisfies light; light receipt does not satisfy full.
    receipt_mode = str(data.get("mode") or "full")
    if mode == "full" and receipt_mode != "full":
        return False
    return True


def write_success_receipt(path: Path, head: str, mode: str) -> None:
    """Atomically record a completed gate while its exclusive lock is still held."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            {"head": head, "status": "passed", "mode": mode},
            sort_keys=True,
        )
        + "\n"
    )
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    os.replace(temporary, path)


@contextmanager
def release_snapshot(root: Path, head: str) -> Iterator[Path]:
    """Run checks from a detached worktree pinned to the inspected commit."""
    with tempfile.TemporaryDirectory(prefix="ai-film-grok-release-") as temporary:
        snapshot = Path(temporary) / "checkout"
        created = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "worktree",
                "add",
                "--detach",
                "--quiet",
                str(snapshot),
                head,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if created.returncode:
            detail = created.stderr.strip() or "git worktree add failed"
            raise ReleaseGateError(f"cannot create release snapshot: {detail}")
        try:
            yield snapshot
        finally:
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "worktree",
                    "remove",
                    "--force",
                    str(snapshot),
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


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


def resolve_mode(explicit: str | None = None) -> str:
    """light = push default; full = make release-check."""
    raw = (explicit or os.environ.get("AIFILM_RELEASE_GATE") or "light").strip().lower()
    if raw in {"full", "heavy", "strict"}:
        return "full"
    return "light"


def _run_docs_check(snapshot: Path) -> int:
    return subprocess.run(
        [
            sys.executable,
            str(snapshot / "scripts" / "sync_project_docs.py"),
            "--check",
        ],
        cwd=snapshot,
        check=False,
    ).returncode


def _run_light_checks(snapshot: Path) -> int:
    """Docs already checked; run doctor core readiness via aifilm if present."""
    aifilm = snapshot / "skills" / "ai-film-grok" / "scripts" / "aifilm"
    if not aifilm.is_file():
        print("[release] light: skip doctor (aifilm missing in snapshot)")
        return 0
    # Prefer JSON doctor and require core_readiness only (not strict advisory).
    result = subprocess.run(
        [str(aifilm), "doctor"],
        cwd=snapshot,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": ""},
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout or "doctor failed\n")
        return result.returncode or 1
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        # Older doctor may print prose; treat exit 0 as pass.
        print("[release] light: doctor exit 0 (non-JSON)")
        return 0
    core = payload.get("core_readiness") or {}
    if core.get("ok") is True:
        print("[release] light: doctor core_readiness ok")
        return 0
    failed = core.get("failed_checks") or payload.get("runtime_lock", {}).get("errors")
    print(f"[release] light: doctor core failed: {failed}", file=sys.stderr)
    return 1


def _run_full_checks(snapshot: Path) -> int:
    return subprocess.run(
        ["make", "release-check"], cwd=snapshot, check=False
    ).returncode


def run_release_gate(
    root: Path,
    *,
    timeout_sec: float = 900,
    mode: str | None = None,
) -> int:
    """Run or safely reuse the pre-push validation for one clean Git HEAD."""
    root = root.expanduser().resolve()
    gate_mode = resolve_mode(mode)
    lock_path = release_lock_path(root)
    receipt_path = release_success_receipt_path(root)
    with exclusive_release_lock(lock_path, timeout_sec=timeout_sec):
        head = current_clean_head(root)
        if successful_receipt_matches(receipt_path, head, gate_mode):
            print(
                f"[release] reusing successful {gate_mode} gate for {head[:12]}"
            )
            return 0
        print(f"[release] mode={gate_mode} head={head[:12]}")
        with release_snapshot(root, head) as snapshot:
            docs_rc = _run_docs_check(snapshot)
            if docs_rc:
                print(
                    "文档已过期；请运行 make sync-docs 并提交后再 push。",
                    file=sys.stderr,
                )
                return docs_rc
            if gate_mode == "full":
                release_rc = _run_full_checks(snapshot)
            else:
                release_rc = _run_light_checks(snapshot)
        if release_rc == 0:
            write_success_receipt(receipt_path, head, gate_mode)
        return release_rc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-sec", type=float, default=900)
    parser.add_argument(
        "--mode",
        choices=("light", "full"),
        default=None,
        help="light (default/pre-push) or full (make release-check)",
    )
    args = parser.parse_args()
    try:
        return run_release_gate(
            Path(__file__).resolve().parents[1],
            timeout_sec=args.timeout_sec,
            mode=args.mode,
        )
    except (ReleaseGateError, TimeoutError) as exc:
        print(f"pre-push blocked: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
