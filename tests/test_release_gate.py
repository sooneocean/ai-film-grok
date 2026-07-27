from __future__ import annotations

import importlib.util
import multiprocessing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_gate", ROOT / "scripts" / "release_gate.py")
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
