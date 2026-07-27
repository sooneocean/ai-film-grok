from __future__ import annotations

import importlib.util
import json
import multiprocessing
import subprocess
from contextlib import nullcontext
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "release_gate", ROOT / "scripts" / "release_gate.py"
)
assert SPEC and SPEC.loader
release_gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_gate)


def _attempt_lock(path: str, queue: multiprocessing.Queue[bool]) -> None:
    try:
        with release_gate.exclusive_release_lock(Path(path), timeout_sec=0.15):
            queue.put(True)
    except TimeoutError:
        queue.put(False)


def test_release_gate_serializes_concurrent_processes(tmp_path: Path) -> None:
    lock = tmp_path / "release.lock"
    queue: multiprocessing.Queue[bool] = multiprocessing.Queue()
    with release_gate.exclusive_release_lock(lock, timeout_sec=0):
        process = multiprocessing.Process(target=_attempt_lock, args=(str(lock), queue))
        process.start()
        process.join(timeout=5)
        assert process.exitcode == 0
        assert queue.get(timeout=1) is False

    with release_gate.exclusive_release_lock(lock, timeout_sec=0):
        pass


def test_release_lock_path_supports_linked_worktrees(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    worktree = tmp_path / "linked-worktree"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-q", str(worktree)], check=True
    )

    lock = release_gate.release_lock_path(worktree)

    assert lock.parent.is_dir()
    assert lock != worktree / ".git" / "ai-film-grok-release-gate.lock"
    with release_gate.exclusive_release_lock(lock, timeout_sec=0):
        assert lock.is_file()


def test_current_clean_head_rejects_tracked_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    tracked = repo / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)

    assert release_gate.current_clean_head(repo)
    tracked.write_text("after\n", encoding="utf-8")
    with pytest.raises(release_gate.ReleaseGateError, match="tracked worktree changes"):
        release_gate.current_clean_head(repo)


def test_release_gate_reuses_only_matching_success_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lock = tmp_path / "release.lock"
    receipt = tmp_path / "success.json"
    head = "a" * 40
    receipt.write_text(json.dumps({"head": head, "status": "passed"}), encoding="utf-8")
    monkeypatch.setattr(release_gate, "release_lock_path", lambda _: lock)
    monkeypatch.setattr(release_gate, "release_success_receipt_path", lambda _: receipt)
    monkeypatch.setattr(release_gate, "current_clean_head", lambda _: head)
    monkeypatch.setattr(
        release_gate, "release_snapshot", lambda *_: nullcontext(tmp_path)
    )

    assert release_gate.run_release_gate(tmp_path, timeout_sec=0) == 0

    monkeypatch.setattr(release_gate, "current_clean_head", lambda _: "b" * 40)
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(release_gate.subprocess, "run", fake_run)
    assert release_gate.run_release_gate(tmp_path, timeout_sec=0) == 0
    assert calls[-1] == ["make", "release-check"]
    assert json.loads(receipt.read_text(encoding="utf-8"))["head"] == "b" * 40


def test_release_snapshot_stays_on_the_checked_head_after_root_advances(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    tracked = repo / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "before"], check=True)
    checked_head = release_gate.current_clean_head(repo)

    with release_gate.release_snapshot(repo, checked_head) as snapshot:
        tracked.write_text("after\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-am", "after", "-q"], check=True
        )
        assert (snapshot / "tracked.txt").read_text(encoding="utf-8") == "before\n"
        assert release_gate.current_clean_head(repo) != checked_head
