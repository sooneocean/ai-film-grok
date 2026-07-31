"""Deferred, capacity-gated queue for the dialogue P2 weapon benchmark.

The queue stores intent locally. It never posts a provider request: a worker
claims a job after the executor-specific capacity gate, runs it manually, and
records the existing human-review receipt before completing the queue job.
"""

from __future__ import annotations

import fcntl
import secrets
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from dialogue_benchmark import MAX_DURATION_SEC, MIN_DURATION_SEC, WEAPON_EXECUTORS, WEAPONS
from runtime_policy import sha256
from util import read_json, utc_now, write_json

_QUEUE_NAME = "dialogue-benchmark-queue.json"
_BENCHMARK_RECEIPT = "dialogue-weapon-benchmark.json"
_PENDING = "pending"
_RUNNING = "running"
_SUCCEEDED = "succeeded"


class DialogueBenchmarkQueueError(RuntimeError):
    pass


def _paths(root: Path | str) -> tuple[Path, Path, Path]:
    base = Path(root).expanduser().resolve()
    return base, base / "receipts" / _BENCHMARK_RECEIPT, base / "receipts" / _QUEUE_NAME


def _benchmark(base: Path, receipt: Path) -> dict[str, Any]:
    value = read_json(receipt) or {}
    try:
        duration = float(value.get("duration_sec"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise DialogueBenchmarkQueueError("DIALOGUE_BENCHMARK_NOT_QUEUEABLE") from exc
    if (
        not isinstance(value, dict)
        or value.get("kind") != "dialogue-weapon-benchmark"
        or value.get("status") != "planned"
        or not MIN_DURATION_SEC <= duration <= MAX_DURATION_SEC
        or set(value.get("weapons") or []) != set(WEAPONS)
        or not isinstance(value.get("line_ids"), list)
        or not value["line_ids"]
    ):
        raise DialogueBenchmarkQueueError("DIALOGUE_BENCHMARK_NOT_QUEUEABLE")
    # The receipt binds this deferred work to a real package prepared under the
    # project root; otherwise a copied receipt could silently target another film.
    package = base / "dialogue-scene-package.json"
    if not package.is_file():
        raise DialogueBenchmarkQueueError("DIALOGUE_PACKAGE_MISSING")
    return value


def _read_queue(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "kind": "dialogue-benchmark-queue", "jobs": []}
    value = read_json(path) or {}
    if value.get("kind") != "dialogue-benchmark-queue" or not isinstance(value.get("jobs"), list):
        raise DialogueBenchmarkQueueError("DIALOGUE_BENCHMARK_QUEUE_INVALID")
    return value


@contextmanager
def _queue_lock(queue_path: Path):
    """Serialize local workers so a benchmark arm cannot be double-claimed."""
    queue_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = queue_path.with_name(f".{queue_path.name}.lock")
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def enqueue(root: Path | str) -> dict[str, Any]:
    """Persist one deferred P2 job per weapon without contacting an executor."""
    base, receipt, queue_path = _paths(root)
    benchmark = _benchmark(base, receipt)
    benchmark_hash = sha256(receipt)
    with _queue_lock(queue_path):
        queue = _read_queue(queue_path)
        existing = [job for job in queue["jobs"] if job.get("benchmark_sha256") == benchmark_hash]
        if not existing:
            jobs = []
            for weapon in WEAPONS:
                jobs.append(
                    {
                        "id": f"dbq_{secrets.token_hex(10)}",
                        "weapon": weapon,
                        "executor": WEAPON_EXECUTORS[weapon],
                        "line_ids": list(benchmark["line_ids"]),
                        "benchmark_sha256": benchmark_hash,
                        "status": _PENDING,
                        "created_at": utc_now(),
                        "execution": "manual_verified_only",
                        "submission": "capacity_checked_at_claim_only",
                    }
                )
            queue["jobs"].extend(jobs)
            queue["updated_at"] = utc_now()
            write_json(queue_path, queue)
            existing = jobs
    return {
        "ok": True,
        "status": "queued",
        "queue_receipt": str(queue_path),
        "benchmark_receipt": str(receipt),
        "jobs": existing,
        "comfy_prompt_submitted": False,
    }


def status(root: Path | str) -> dict[str, Any]:
    _, _, queue_path = _paths(root)
    queue = _read_queue(queue_path)
    jobs = queue["jobs"]
    return {
        "ok": True,
        "queue_receipt": str(queue_path),
        "jobs": jobs,
        "counts": {
            state: sum(job.get("status") == state for job in jobs)
            for state in (_PENDING, _RUNNING, _SUCCEEDED)
        },
    }


def claim(root: Path | str) -> dict[str, Any]:
    """Claim one deferred arm with the capacity gate required by its executor."""
    base, receipt, queue_path = _paths(root)
    _benchmark(base, receipt)
    with _queue_lock(queue_path):
        queue = _read_queue(queue_path)
        if any(job.get("status") == _RUNNING for job in queue["jobs"]):
            raise DialogueBenchmarkQueueError("DIALOGUE_BENCHMARK_QUEUE_ALREADY_RUNNING")
        job = next((item for item in queue["jobs"] if item.get("status") == _PENDING), None)
        if not isinstance(job, dict):
            raise DialogueBenchmarkQueueError("DIALOGUE_BENCHMARK_QUEUE_EMPTY")
        executor = str(job.get("executor") or WEAPON_EXECUTORS.get(str(job.get("weapon")), ""))
        if executor == "comfy":
            from comfy_video import ComfyVideoError, submission_capacity
            from config_loader import get_config

            base_url = str(get_config().comfyui_base_url or "").strip()
            if not base_url:
                return {"ok": False, "status": "deferred", "reason": "COMFY_BASE_URL_UNCONFIGURED"}
            try:
                capacity = submission_capacity(base_url)
            except ComfyVideoError as exc:
                return {
                    "ok": False,
                    "status": "deferred",
                    "reason": "COMFY_CAPACITY_UNAVAILABLE",
                    "detail": str(exc),
                }
            if not capacity.get("ok"):
                return {
                    "ok": False,
                    "status": "deferred",
                    "reason": "COMFY_CAPACITY_BLOCKED",
                    "capacity": capacity,
                }
        elif executor == "frw":
            capacity = {"ok": True, "status": "not_required", "executor": "frw"}
        else:
            raise DialogueBenchmarkQueueError("DIALOGUE_BENCHMARK_EXECUTOR_INVALID")
        job.update(
            {
                "status": _RUNNING,
                "claimed_at": utc_now(),
                "claim_token": secrets.token_hex(16),
                "executor": executor,
            }
        )
        queue["updated_at"] = utc_now()
        write_json(queue_path, queue)
    return {
        "ok": True,
        "status": "claimed",
        "job": job,
        "capacity": capacity,
        "comfy_prompt_submitted": False,
    }


def complete(root: Path | str, *, job_id: str, claim_token: str) -> dict[str, Any]:
    """Complete only after the corresponding human-reviewed benchmark arm exists."""
    base, receipt, queue_path = _paths(root)
    report = _benchmark(base, receipt)
    with _queue_lock(queue_path):
        queue = _read_queue(queue_path)
        job = next((item for item in queue["jobs"] if item.get("id") == job_id), None)
        if (
            not isinstance(job, dict)
            or job.get("status") != _RUNNING
            or job.get("claim_token") != claim_token
        ):
            raise DialogueBenchmarkQueueError("DIALOGUE_BENCHMARK_QUEUE_CLAIM_INVALID")
        arm = next(
            (item for item in report.get("arms") or [] if item.get("weapon") == job.get("weapon")),
            None,
        )
        artifact = str(arm.get("artifact") or "") if isinstance(arm, dict) else ""
        artifact_sha = str(arm.get("artifact_sha256") or "") if isinstance(arm, dict) else ""
        artifact_path = (base / artifact).resolve() if artifact else None
        if (
            not isinstance(arm, dict)
            or arm.get("status") != "reviewed"
            or not str(arm.get("reviewer") or "").strip()
            or not str(arm.get("review_note") or "").strip()
            or len(artifact_sha) != 64
            or not artifact_path
            or not artifact_path.is_relative_to(base)
            or not artifact_path.is_file()
            or sha256(artifact_path) != artifact_sha
        ):
            raise DialogueBenchmarkQueueError("DIALOGUE_BENCHMARK_ARM_REVIEW_EVIDENCE_INVALID")
        job.update(
            {
                "status": _SUCCEEDED,
                "completed_at": utc_now(),
                "review_artifact_sha256": artifact_sha,
            }
        )
        job.pop("claim_token", None)
        queue["updated_at"] = utc_now()
        write_json(queue_path, queue)
    return {"ok": True, "status": "succeeded", "job": job}
