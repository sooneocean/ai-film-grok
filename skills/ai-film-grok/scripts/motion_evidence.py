"""Fail-closed binding between an I2V queue completion and its registered clip."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from media_queue import STATUS_SUCCEEDED, MediaQueue
from security_policy import validate_identifier
from util import sha256_file, utc_now, write_json


class MotionEvidenceError(ValueError):
    pass


def build_motion_generation_evidence(
    root: Path | str,
    *,
    shot_id: str,
    clip: Path | str,
    source_endpoint: str,
    queue_job_id: str | None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Bind a clip to a terminal queue receipt; dry-run is never delivery evidence."""
    base = Path(root).expanduser().resolve()
    sid = validate_identifier(shot_id, field="shot id")
    media = Path(clip).expanduser().resolve()
    if not media.is_file():
        raise MotionEvidenceError("motion output is missing")
    output_sha = sha256_file(media)
    evidence: dict[str, Any] = {
        "schema_version": 1,
        "kind": "motion-generation-evidence",
        "shot_id": sid,
        "source_endpoint": source_endpoint,
        "clip": {"path": str(media), "sha256": output_sha},
        "created_at": utc_now(),
        "dry_run": bool(dry_run),
        "delivery_eligible": False,
    }
    if dry_run:
        evidence["status"] = "dry-run"
        evidence["reason"] = "dry-run output is intentionally not provider delivery evidence"
    else:
        if not queue_job_id:
            raise MotionEvidenceError("provider-backed motion requires --queue-job-id")
        state = MediaQueue(base).state()
        job = next((j for j in state.get("jobs") or [] if j.get("id") == queue_job_id), None)
        if not isinstance(job, dict) or job.get("status") != STATUS_SUCCEEDED:
            raise MotionEvidenceError("queue job is missing or not succeeded")
        if str(job.get("shot_id") or "") != sid:
            raise MotionEvidenceError("queue job belongs to another shot")
        if str(job.get("operation") or "") != source_endpoint:
            raise MotionEvidenceError("queue operation does not match source endpoint")
        source_contract = job.get("source_contract")
        if isinstance(source_contract, dict):
            try:
                from production_chain import ProductionChainError, require_current_queue_contract

                require_current_queue_contract(base, source_contract)
            except ProductionChainError as exc:
                raise MotionEvidenceError(str(exc)) from exc
        else:
            from production_chain import canonical_contract_required

            if canonical_contract_required(base):
                raise MotionEvidenceError(
                    "queue job source contract is missing for a canonical project"
                )
        receipt = job.get("receipt") if isinstance(job.get("receipt"), dict) else {}
        if receipt.get("output_sha256") != output_sha:
            raise MotionEvidenceError("queue receipt output hash does not match clip")
        if not isinstance(receipt.get("qa"), dict) or receipt["qa"].get("ok") is not True:
            raise MotionEvidenceError("queue receipt lacks successful media QA")
        inputs = job.get("inputs") if isinstance(job.get("inputs"), list) else []
        input_hashes = [str(item.get("sha256")) for item in inputs if isinstance(item, dict)]
        minimum_inputs = 2 if source_endpoint == "reference_to_video" else 1
        if len(input_hashes) < minimum_inputs or any(not item for item in input_hashes):
            raise MotionEvidenceError(
                f"queue receipt lacks {minimum_inputs} hash-bound input frame(s) for {source_endpoint}"
            )
        evidence.update(
            {
                "status": "succeeded",
                "delivery_eligible": True,
                "queue": {
                    "job_id": queue_job_id,
                    "provider_request_id": receipt.get("provider_request_id"),
                    "generation_id": receipt.get("generation_id"),
                    "input_hashes": input_hashes,
                    "receipt_sha256": output_sha,
                    "source_contract_sha256": source_contract.get("contract_sha256")
                    if isinstance(source_contract, dict)
                    else None,
                },
            }
        )
    path = base / "receipts" / "motion-evidence" / f"{sid}.json"
    write_json(path, evidence)
    evidence["path"] = str(path)
    evidence["sha256"] = sha256_file(path)
    return evidence


def motion_evidence_is_current(evidence: object, *, clip: Path | str) -> bool:
    if not isinstance(evidence, dict) or evidence.get("kind") != "motion-generation-evidence":
        return False
    media = Path(clip).expanduser().resolve()
    record = evidence.get("clip") if isinstance(evidence.get("clip"), dict) else {}
    return bool(
        evidence.get("delivery_eligible") is True
        and media.is_file()
        and record.get("sha256") == sha256_file(media)
    )
