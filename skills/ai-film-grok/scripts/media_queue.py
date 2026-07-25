#!/usr/bin/env python3
"""Persistent single-concurrency queue and capability receipts for Grok media tools."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from media_qa import ALLOWED_VIDEO_ENDPOINTS, MediaQAError, analyze_media
from production_gates import ProductionGateError, assert_pilot_allows_add
from runtime_policy import sha256
from security_policy import (
    SecurityPolicyError,
    atomic_write_text,
    safe_output_path,
    safe_workspace_directory,
    validate_identifier,
)
from util import utc_now

OPERATIONS = frozenset({"image_gen", "image_edit", "image_to_video", "reference_to_video"})
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
TERMINAL_STATUSES = frozenset({STATUS_SUCCEEDED, STATUS_FAILED})
# Typed fail reasons — agents must use these instead of hand-editing queue JSON
FAIL_REASONS = frozenset({"moderation", "motion", "rate_limit", "decode", "other"})
# Default backoff seconds by reason when retryable
REASON_BACKOFF_SEC = {
    "moderation": 0,  # do not auto-spin; requeue after soft still
    "motion": 5,
    "rate_limit": 90,  # Kei 2026-07-16: 45s still hit 503; give Imagine more room
    "decode": 10,
    "other": 15,
}


class QueueError(RuntimeError):
    pass


def _usage_binding(root: Path, generation_id: str, job_id: str) -> dict[str, Any]:
    """Require a completed usage record before binding provider media to a job."""
    try:
        from generation_usage import usage_list

        records = usage_list(root, generation_id=generation_id).get("records") or []
    except (OSError, ValueError) as exc:
        raise QueueError(f"cannot read generation usage for {generation_id}: {exc}") from exc
    if len(records) != 1 or not isinstance(records[0], dict):
        raise QueueError(f"generation usage receipt missing for {generation_id}")
    record = records[0]
    recorded_job = record.get("job_id")
    if recorded_job not in {None, "", job_id}:
        raise QueueError(
            f"generation {generation_id} belongs to job {recorded_job!r}, not {job_id!r}"
        )
    if record.get("status") not in {"succeeded", "failed", "moderated"}:
        raise QueueError(f"generation {generation_id} is not terminal in usage receipt")
    usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
    return {
        "generation_id": generation_id,
        "status": record.get("status"),
        "measurement": record.get("measurement", "unknown"),
        "provider_request_id": record.get("provider_request_id"),
        "usage": usage,
        "cost_in_usd_ticks": usage.get("cost_in_usd_ticks"),
    }


def normalize_fail_reason(value: object) -> str:
    """Map free-text or enum to a FAIL_REASONS member."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return "other"
    text = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if text in FAIL_REASONS:
        return text
    # Aliases from provider / QA messages
    if "moderat" in text or "content_moderat" in text or "nsfw" in text:
        return "moderation"
    if "motion" in text or "static" in text:
        return "motion"
    if "rate" in text or "429" in text or "resource_exhausted" in text or "too_many" in text:
        return "rate_limit"
    if "decode" in text or "ffprobe" in text or "corrupt" in text:
        return "decode"
    return "other"


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class MediaQueue:
    def __init__(self, root: Path | str, *, budget_units: int = 20):
        if budget_units < 1 or budget_units > 10_000:
            raise QueueError("budget_units must be between 1 and 10000")
        self.budget_units = budget_units
        self.root = Path(root).expanduser().resolve()
        try:
            self.receipts = safe_workspace_directory(
                self.root, "receipts", field="film receipts directory"
            )
        except SecurityPolicyError as exc:
            raise QueueError(str(exc)) from exc
        self.receipts.mkdir(parents=True, exist_ok=True)
        try:
            self.path = safe_output_path(
                self.receipts, "media-queue.json", suffixes={".json"}, field="media queue"
            )
            self.lock_path = safe_output_path(
                self.receipts, ".media-queue.lock", suffixes={".lock"}, field="media queue lock"
            )
        except SecurityPolicyError as exc:
            raise QueueError(str(exc)) from exc

    @contextmanager
    def _locked(self) -> Iterator[None]:
        with self.lock_path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {
                "schema_version": 1,
                "updated_at": utc_now(),
                "policy": {"max_concurrency": 1, "budget_units": self.budget_units},
                "jobs": [],
            }
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise QueueError(f"media queue is corrupt: {exc}") from exc
        if not isinstance(value, dict) or not isinstance(value.get("jobs"), list):
            raise QueueError("media queue has invalid shape")
        return value

    def _write(self, state: dict[str, Any]) -> None:
        state["updated_at"] = utc_now()
        atomic_write_text(self.path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")

    def state(self) -> dict[str, Any]:
        with self._locked():
            return self._read()

    def set_budget(self, units: int) -> dict[str, Any]:
        if units < 1 or units > 10_000:
            raise QueueError("budget units must be between 1 and 10000")
        with self._locked():
            state = self._read()
            state.setdefault("policy", {})["budget_units"] = units
            self._write(state)
            return state

    def metrics(self, state: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self.state() if state is None else state
        counts: dict[str, int] = {}
        attempts = 0
        durations: list[float] = []
        for job in state["jobs"]:
            status = str(job.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
            attempts += int(job.get("attempts") or 0)
            if job.get("claimed_at") and job.get("completed_at"):
                durations.append(
                    max(
                        0.0,
                        (
                            _parse_time(job["completed_at"]) - _parse_time(job["claimed_at"])
                        ).total_seconds(),
                    )
                )
        terminal = sum(counts.get(status, 0) for status in TERMINAL_STATUSES)
        result = {
            "counts": counts,
            "jobs": len(state["jobs"]),
            "attempts": attempts,
            "success_rate": round(counts.get(STATUS_SUCCEEDED, 0) / terminal, 4)
            if terminal
            else None,
            "mean_run_seconds": round(sum(durations) / len(durations), 3) if durations else None,
            "budget_units": int(
                (state.get("policy") or {}).get("budget_units") or self.budget_units
            ),
            "budget_remaining": max(
                0,
                int((state.get("policy") or {}).get("budget_units") or self.budget_units)
                - len(state["jobs"]),
            ),
        }
        try:
            from generation_usage import usage_status

            usage = usage_status(self.root)
            result["actual_generation_requests"] = usage.get("requests_total", 0)
            result["actual_generation_status_counts"] = usage.get("status_counts", {})
            result["actual_generation_unknown_cost_requests"] = usage.get(
                "unknown_cost_requests", 0
            )
        except (OSError, ValueError):
            result["actual_generation_requests"] = 0
            result["actual_generation_status_counts"] = {}
            result["actual_generation_unknown_cost_requests"] = 0
        return result

    def add_job(
        self,
        *,
        shot_id: str,
        operation: str,
        prompt_file: Path,
        inputs: list[Path],
        max_attempts: int = 3,
        allow_without_pilot: bool = False,
        assembly_receipt: Path | None = None,
        is_canary: bool = False,
        canary_group_id: str | None = None,
        seed_offset: int = 0,
    ) -> dict[str, Any]:
        try:
            shot_id = validate_identifier(shot_id, field="shot id")
        except SecurityPolicyError as exc:
            raise QueueError(str(exc)) from exc
        if operation not in OPERATIONS:
            raise QueueError(f"unknown media operation {operation!r}")
        prompt = prompt_file.expanduser().resolve()
        if not prompt.is_file():
            raise QueueError(f"prompt file is missing: {prompt}")
        resolved_inputs = [path.expanduser().resolve() for path in inputs]
        if any(not path.is_file() for path in resolved_inputs):
            raise QueueError("every media input must be an existing file")
        if max_attempts < 1 or max_attempts > 10:
            raise QueueError("max_attempts must be between 1 and 10")
        # Shot must exist in film-spec when present (no ghost queue after write-spec)
        spec_path = self.root / "film-spec.json"
        if spec_path.is_file():
            try:
                from narrative_control import NarrativeControlError, assert_projection_ready

                assert_projection_ready(self.root, require_locked=True)
            except NarrativeControlError as exc:
                raise QueueError(f"{exc.code}: {exc}") from exc
            try:
                import json as _json

                raw_spec = _json.loads(spec_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise QueueError(f"cannot read film-spec.json: {exc}") from exc
            known_ids: set[str] = set()
            if isinstance(raw_spec, dict):
                try:
                    from film_spec import validate_film_spec

                    for s in validate_film_spec(raw_spec, assign_missing_ids=False):
                        known_ids.add(str(s["id"]))
                except Exception:
                    for scene in raw_spec.get("scenes") or []:
                        if not isinstance(scene, dict):
                            continue
                        for sh in scene.get("shots") or []:
                            if isinstance(sh, dict) and sh.get("id"):
                                known_ids.add(str(sh["id"]))
            if known_ids and shot_id not in known_ids:
                raise QueueError(
                    f"shot_id {shot_id!r} is not in film-spec "
                    f"(known={sorted(known_ids)}). write-spec first; do not queue ghost shots."
                )
        prompt_hash = sha256(prompt)
        input_records = [{"path": str(path), "sha256": sha256(path)} for path in resolved_inputs]
        identity = json.dumps(
            {
                "shot_id": shot_id,
                "operation": operation,
                "prompt": prompt_hash,
                "inputs": input_records,
                "is_canary": is_canary,
                "seed_offset": seed_offset,
            },
            sort_keys=True,
        ).encode("utf-8")
        canary_suffix = f"-canary{seed_offset}" if is_canary else ""
        job_id = f"{shot_id}-{hashlib.sha256(identity).hexdigest()[:16]}{canary_suffix}"
        with self._locked():
            state = self._read()
            existing = next((job for job in state["jobs"] if job.get("id") == job_id), None)
            if existing:
                return existing
            existing_shot_ids = {
                str(job.get("shot_id")) for job in state["jobs"] if job.get("shot_id")
            }
            try:
                assert_pilot_allows_add(
                    self.root,
                    shot_id=shot_id,
                    existing_shot_ids=existing_shot_ids,
                    force=allow_without_pilot,
                )
            except ProductionGateError as exc:
                raise QueueError(str(exc)) from exc
            effective_budget = int(
                (state.get("policy") or {}).get("budget_units") or self.budget_units
            )
            if len(state["jobs"]) >= effective_budget:
                raise QueueError(
                    f"generation-unit budget exhausted ({len(state['jobs'])}/{effective_budget}); "
                    "use the budget command to raise it explicitly before adding work"
                )
            job = {
                "id": job_id,
                "shot_id": shot_id,
                "operation": operation,
                "prompt_file": str(prompt),
                "prompt_sha256": prompt_hash,
                "inputs": input_records,
                "status": STATUS_PENDING,
                "attempts": 0,
                "max_attempts": max_attempts,
                "next_attempt_at": utc_now(),
                "created_at": utc_now(),
                "is_canary": is_canary,
                "seed_offset": seed_offset,
            }
            if canary_group_id:
                job["canary_group_id"] = canary_group_id
            if assembly_receipt:
                job["assembly_receipt"] = str(assembly_receipt.expanduser().resolve())
            state["jobs"].append(job)
            self._write(state)
            return job

    def add_canary_pair(
        self,
        *,
        shot_id: str,
        operation: str,
        prompt_file: Path,
        inputs: list[Path],
        max_attempts: int = 3,
        allow_without_pilot: bool = False,
        seed_offset: int = 101,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Enqueue primary job and canary speculative mutation job in parallel."""
        group_id = f"canary_grp_{shot_id}_{secrets.token_hex(4)}"
        primary = self.add_job(
            shot_id=shot_id,
            operation=operation,
            prompt_file=prompt_file,
            inputs=inputs,
            max_attempts=max_attempts,
            allow_without_pilot=allow_without_pilot,
            is_canary=False,
            canary_group_id=group_id,
        )
        canary = self.add_job(
            shot_id=shot_id,
            operation=operation,
            prompt_file=prompt_file,
            inputs=inputs,
            max_attempts=max_attempts,
            allow_without_pilot=allow_without_pilot,
            is_canary=True,
            canary_group_id=group_id,
            seed_offset=seed_offset,
        )
        return primary, canary

    def claim(self, *, now: str | None = None) -> dict[str, Any]:
        current = _parse_time(now or utc_now())
        with self._locked():
            state = self._read()
            if any(job.get("status") == STATUS_RUNNING for job in state["jobs"]):
                raise QueueError("single-concurrency policy: another media job is already running")
            eligible = [
                job
                for job in state["jobs"]
                if job.get("status") == STATUS_PENDING
                and _parse_time(job.get("next_attempt_at") or utc_now()) <= current
            ]
            if not eligible:
                raise QueueError("no media job is eligible to run")
            job = eligible[0]
            job["status"] = STATUS_RUNNING
            job["attempts"] = int(job.get("attempts") or 0) + 1
            job["claimed_at"] = current.replace(microsecond=0).isoformat()
            job["claim_token"] = secrets.token_hex(16)
            self._write(state)
        try:
            from pipeline_events import append_event

            append_event(
                self.root,
                stage="i2v",
                phase="claimed",
                shot_id=str(job.get("shot_id") or ""),
                retry_of=str(job.get("id") or "") if int(job.get("attempts") or 0) > 1 else None,
            )
        except OSError:
            pass
        return job

    def _running_job(self, state: dict[str, Any], job_id: str, claim_token: str) -> dict[str, Any]:
        job = next((item for item in state["jobs"] if item.get("id") == job_id), None)
        if not job or job.get("status") != STATUS_RUNNING or job.get("claim_token") != claim_token:
            raise QueueError("job is not running under this claim token")
        return job

    def fail(
        self,
        job_id: str,
        *,
        claim_token: str,
        error: str,
        retryable: bool,
        reason: str | None = None,
        now: str | None = None,
    ) -> dict[str, Any]:
        current = _parse_time(now or utc_now())
        reason_norm = normalize_fail_reason(reason if reason is not None else error)
        with self._locked():
            state = self._read()
            job = self._running_job(state, job_id, claim_token)
            attempts = int(job["attempts"])
            job["fail_reason"] = reason_norm
            job["last_error"] = str(error)[:1000]
            # moderation: do not auto-retry spinning the same still; mark failed unless
            # caller forces retryable and still has attempts (soft still then requeue)
            auto_retry = retryable and attempts < int(job["max_attempts"])
            if reason_norm == "moderation" and retryable:
                # stay failed until agent requeues after soft still / new inputs
                auto_retry = False
            if auto_retry:
                base = REASON_BACKOFF_SEC.get(reason_norm, 15)
                if reason_norm == "rate_limit":
                    delay = max(base, min(60 * (2 ** (attempts - 1)), 1800))
                else:
                    delay = min(max(base, 5 * (2 ** (attempts - 1))), 1800)
                job["status"] = STATUS_PENDING
                job["next_attempt_at"] = (
                    (current + timedelta(seconds=delay)).replace(microsecond=0).isoformat()
                )
            else:
                job["status"] = STATUS_FAILED
            job.setdefault("retry_history", []).append(
                {
                    "attempt": attempts,
                    "reason": reason_norm,
                    "retryable": bool(retryable),
                    "status_after": job["status"],
                    "next_attempt_at": job.get("next_attempt_at"),
                    "error": str(error)[:1000],
                    "recorded_at": utc_now(),
                }
            )
            job.pop("claim_token", None)
            self._write(state)
        try:
            from pipeline_events import append_event

            append_event(
                self.root,
                stage="i2v",
                phase="failed",
                shot_id=str(job.get("shot_id") or ""),
                error_code=reason_norm,
            )
        except OSError:
            pass
        return job

    def requeue(
        self,
        job_id: str,
        *,
        reason: str | None = None,
        reset_attempts: bool = False,
        now: str | None = None,
    ) -> dict[str, Any]:
        """Return a failed/pending/running-stale job to pending without hand-editing JSON.

        Clears claim_token. Optionally records fail_reason for agent playbooks.
        Does not require claim_token (explicit operator action after soft still / rate wait).
        """
        current = _parse_time(now or utc_now())
        with self._locked():
            state = self._read()
            job = next((item for item in state["jobs"] if item.get("id") == job_id), None)
            if not job:
                raise QueueError(f"unknown job id: {job_id}")
            status = str(job.get("status") or "")
            if status == STATUS_SUCCEEDED:
                raise QueueError("cannot requeue a succeeded job")
            if status == STATUS_RUNNING:
                raise QueueError(
                    "job is running under a claim; fail it first or wait for reconcile"
                )
            if reason is not None:
                job["fail_reason"] = normalize_fail_reason(reason)
            job["status"] = STATUS_PENDING
            job["next_attempt_at"] = current.replace(microsecond=0).isoformat()
            job.pop("claim_token", None)
            if reset_attempts:
                job["attempts"] = 0
            job["requeued_at"] = current.replace(microsecond=0).isoformat()
            job.setdefault("retry_history", []).append(
                {
                    "attempt": int(job.get("attempts") or 0),
                    "reason": normalize_fail_reason(reason) if reason is not None else None,
                    "retryable": True,
                    "status_after": STATUS_PENDING,
                    "next_attempt_at": job["next_attempt_at"],
                    "manual": True,
                    "recorded_at": utc_now(),
                }
            )
            self._write(state)
            return job

    def complete(
        self,
        job_id: str,
        *,
        claim_token: str,
        output: Path,
        endpoint: str,
        provider_request_id: str | None = None,
        generation_id: str | None = None,
    ) -> dict[str, Any]:
        media = output.expanduser().resolve()
        if endpoint not in ALLOWED_VIDEO_ENDPOINTS:
            raise QueueError(
                f"completion endpoint must be one of {sorted(ALLOWED_VIDEO_ENDPOINTS)}"
            )
        qa = analyze_media(media, require_audio=False, require_motion=True)
        if not qa.get("ok"):
            raise QueueError(f"media output failed decode/duration/motion QA: {qa.get('errors')}")
        with self._locked():
            state = self._read()
            job = self._running_job(state, job_id, claim_token)
            if job.get("operation") != endpoint:
                raise QueueError(
                    f"job operation {job.get('operation')} does not match endpoint {endpoint}"
                )
            usage_binding = None
            if generation_id:
                usage_binding = _usage_binding(self.root, generation_id, job_id)
                if usage_binding["status"] != STATUS_SUCCEEDED:
                    raise QueueError(
                        f"generation {generation_id} ended as {usage_binding['status']}, not succeeded"
                    )
            job["status"] = STATUS_SUCCEEDED
            job["completed_at"] = utc_now()
            job["receipt"] = {
                "endpoint": endpoint,
                "provider_request_id": provider_request_id,
                "generation_id": generation_id,
                "output": str(media),
                "output_sha256": sha256(media),
                "qa": qa,
            }
            if usage_binding is not None:
                job["receipt"]["generation_usage"] = usage_binding
            job["attempts_completed"] = int(job.get("attempts") or 0)
            job.pop("claim_token", None)
            self._write(state)
        try:
            from pipeline_events import append_event

            append_event(
                self.root, stage="i2v", phase="completed", shot_id=str(job.get("shot_id") or "")
            )
        except OSError:
            pass
        return job

    def reconcile(self, *, stale_after_seconds: int = 1800, now: str | None = None) -> list[str]:
        current = _parse_time(now or utc_now())
        reset: list[str] = []
        with self._locked():
            state = self._read()
            for job in state["jobs"]:
                if job.get("status") != STATUS_RUNNING or not job.get("claimed_at"):
                    continue
                if current - _parse_time(job["claimed_at"]) > timedelta(
                    seconds=stale_after_seconds
                ):
                    job["status"] = STATUS_PENDING
                    job["next_attempt_at"] = current.replace(microsecond=0).isoformat()
                    job.pop("claim_token", None)
                    reset.append(job["id"])
            if reset:
                self._write(state)
        return reset


def record_capability(root: Path | str, *, endpoint: str, media: Path) -> dict[str, Any]:
    if endpoint not in ALLOWED_VIDEO_ENDPOINTS:
        raise QueueError(f"unknown video endpoint {endpoint}")
    film_root = Path(root).expanduser().resolve()
    receipts = safe_workspace_directory(film_root, "receipts", field="film receipts directory")
    receipts.mkdir(parents=True, exist_ok=True)
    path = safe_output_path(
        receipts, "capabilities.json", suffixes={".json"}, field="capability receipt"
    )
    qa = analyze_media(media, require_audio=False, require_motion=True)
    result = {
        "endpoint": endpoint,
        "checked_at": utc_now(),
        "media_sha256": sha256(media),
        "qa": qa,
    }
    state = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.is_file()
        else {"schema_version": 1, "checks": []}
    )
    state.setdefault("checks", []).append(result)
    state["latest"] = result
    atomic_write_text(path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    if not qa.get("ok"):
        raise QueueError(f"capability canary failed decode/duration/motion QA: {qa.get('errors')}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ai-film-grok persistent media queue")
    parser.add_argument("--budget-units", type=int, default=20)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("--root", required=True)
    add.add_argument("--shot-id", required=True)
    add.add_argument("--operation", required=True, choices=sorted(OPERATIONS))
    add.add_argument("--prompt-file", required=True)
    add.add_argument("--input", action="append", default=[])
    add.add_argument("--max-attempts", type=int, default=3)
    add.add_argument(
        "--allow-without-pilot",
        action="store_true",
        help="Skip pilot user-approval gate (emergency / unit tests only)",
    )
    add.add_argument(
        "--assembly-receipt", help="Path to prompt_assembly_shot.json receipt for traceability"
    )
    claim = sub.add_parser("claim")
    claim.add_argument("--root", required=True)
    status = sub.add_parser("status")
    status.add_argument("--root", required=True)
    budget = sub.add_parser("budget")
    budget.add_argument("--root", required=True)
    budget.add_argument("--units", required=True, type=int)
    complete = sub.add_parser("complete")
    complete.add_argument("--root", required=True)
    complete.add_argument("--job-id", required=True)
    complete.add_argument("--claim-token", required=True)
    complete.add_argument("--output", required=True)
    complete.add_argument("--endpoint", required=True, choices=sorted(ALLOWED_VIDEO_ENDPOINTS))
    complete.add_argument("--provider-request-id")
    complete.add_argument("--generation-id")
    fail = sub.add_parser("fail")
    fail.add_argument("--root", required=True)
    fail.add_argument("--job-id", required=True)
    fail.add_argument("--claim-token", required=True)
    fail.add_argument("--error", required=True)
    fail.add_argument(
        "--reason",
        choices=sorted(FAIL_REASONS),
        default=None,
        help="typed fail reason: moderation|motion|rate_limit|decode|other",
    )
    fail.add_argument("--terminal", action="store_true")
    requeue = sub.add_parser(
        "requeue", help="Return failed/pending job to pending (no hand-edit JSON)"
    )
    requeue.add_argument("--root", required=True)
    requeue.add_argument("--job-id", required=True)
    requeue.add_argument(
        "--reason",
        choices=sorted(FAIL_REASONS),
        default=None,
        help="optional reason stamp on requeue",
    )
    requeue.add_argument(
        "--reset-attempts",
        action="store_true",
        help="reset attempts counter (e.g. after soft still + new prompt)",
    )
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("--root", required=True)
    reconcile.add_argument("--stale-after", type=int, default=1800)
    canary = sub.add_parser("capability")
    canary.add_argument("--root", required=True)
    canary.add_argument("--endpoint", required=True, choices=sorted(ALLOWED_VIDEO_ENDPOINTS))
    canary.add_argument("--media", required=True)
    args = parser.parse_args(argv)
    try:
        queue = MediaQueue(args.root, budget_units=args.budget_units)
        if args.command == "add":
            result = queue.add_job(
                shot_id=args.shot_id,
                operation=args.operation,
                prompt_file=Path(args.prompt_file),
                inputs=[Path(value) for value in args.input],
                max_attempts=args.max_attempts,
                allow_without_pilot=bool(getattr(args, "allow_without_pilot", False)),
                assembly_receipt=Path(args.assembly_receipt) if args.assembly_receipt else None,
            )
        elif args.command == "claim":
            result = queue.claim()
        elif args.command == "status":
            state = queue.state()
            result = {"state": state, "metrics": queue.metrics(state)}
        elif args.command == "budget":
            state = queue.set_budget(args.units)
            result = {"policy": state["policy"], "metrics": queue.metrics(state)}
        elif args.command == "complete":
            result = queue.complete(
                args.job_id,
                claim_token=args.claim_token,
                output=Path(args.output),
                endpoint=args.endpoint,
                provider_request_id=args.provider_request_id,
                generation_id=args.generation_id,
            )
        elif args.command == "fail":
            result = queue.fail(
                args.job_id,
                claim_token=args.claim_token,
                error=args.error,
                reason=args.reason,
                retryable=not args.terminal,
            )
        elif args.command == "requeue":
            result = queue.requeue(
                args.job_id,
                reason=args.reason,
                reset_attempts=args.reset_attempts,
            )
        elif args.command == "reconcile":
            result = {"reset": queue.reconcile(stale_after_seconds=args.stale_after)}
        else:
            result = record_capability(args.root, endpoint=args.endpoint, media=Path(args.media))
        print(json.dumps({"ok": True, "result": result}, ensure_ascii=False, indent=2))
        return 0
    except (MediaQAError, QueueError, SecurityPolicyError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
