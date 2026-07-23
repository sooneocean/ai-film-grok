#!/usr/bin/env python3
"""Hash-bound professional production stages and human lock evidence."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from approval_ledger import approval_is_current, read_approval_ledger
from production_book import read_production_book, stable_content_hash
from util import read_json, sha256_file, write_json

STAGE_ORDER = (
    "concept_lock",
    "script_lock",
    "department_look_lock",
    "shot_animatic_lock",
    "pilot_approval",
    "bulk",
    "dailies_review",
    "selects_rough_cut",
    "picture_lock",
    "post_locks",
    "master_lock",
)
ART_STAGES = {
    "concept_lock",
    "script_lock",
    "department_look_lock",
    "shot_animatic_lock",
}
PAID_STAGES = {"pilot_approval", "bulk"}
LEDGER_PATH = Path("receipts/director-stage-locks.json")
HUMAN_APPROVER_TYPES = {"human", "user"}


class StageGateError(ValueError):
    """Stage evidence is malformed, stale, or out of order."""


def _file_sha256(path: Path) -> str:
    return sha256_file(path)


def _resolve_ref(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root):
        raise StageGateError(f"input ref escapes production root: {relative}")
    if not candidate.is_file():
        raise StageGateError(f"stage input is missing: {relative}")
    return candidate


def hash_input_refs(root: Path | str, input_refs: Mapping[str, str]) -> dict[str, str]:
    base = Path(root).expanduser().resolve()
    if not input_refs:
        raise StageGateError("stage lock requires exact input refs or hashes")
    return {
        str(name): _file_sha256(_resolve_ref(base, str(relative)))
        for name, relative in input_refs.items()
    }


def _ledger_path(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / LEDGER_PATH


def read_stage_locks(root: Path | str) -> dict[str, Any]:
    ledger = read_json(_ledger_path(root)) or {}
    ledger.setdefault("schema_version", 1)
    ledger.setdefault("kind", "director-stage-locks")
    ledger.setdefault("revision", 0)
    ledger.setdefault("locks", {})
    ledger.setdefault("events", [])
    return ledger


def _rigor(root: Path | str) -> str:
    try:
        return str(read_production_book(root).get("rigor") or "legacy")
    except FileNotFoundError:
        return "legacy"


def _stage_kind(stage: str) -> str:
    if stage in ART_STAGES:
        return "art"
    if stage in PAID_STAGES:
        return "paid"
    return "integrity"


def _approval_for_id(root: Path | str, approval_id: str) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in read_approval_ledger(root).get("approvals") or []
            if item.get("approval_id") == approval_id
        ),
        None,
    )


def _validate_approval(
    root: Path | str,
    *,
    stage: str,
    approval_id: str,
    input_hashes: Mapping[str, str],
) -> dict[str, Any]:
    approval = _approval_for_id(root, approval_id)
    if approval is None:
        raise StageGateError("stage lock approval does not exist")
    if approval.get("revoked") is True:
        raise StageGateError("stage lock approval was revoked")
    if approval.get("project_binding_current") is not True:
        raise StageGateError("stage lock approval belongs to another project")
    if approval.get("ledger_integrity_current") is not True:
        raise StageGateError("stage lock approval ledger has no current integrity hash")
    if approval.get("approver_type") not in HUMAN_APPROVER_TYPES:
        raise StageGateError("stage lock requires a human/user approval")
    if approval.get("scope") != f"stage:{stage}" or approval.get("approval_type") != "stage_lock":
        raise StageGateError("approval scope/type does not match the stage lock")
    if not approval_is_current(approval, input_hashes)["ok"]:
        raise StageGateError("stage approval is not current for exact input hashes")
    return approval


def _current_hashes(root: Path, lock: Mapping[str, Any]) -> dict[str, str]:
    recorded = dict(lock.get("input_hashes") or {})
    refs = dict(lock.get("input_refs") or {})
    if not refs:
        return recorded
    current = dict(recorded)
    for name, relative in refs.items():
        current[str(name)] = _file_sha256(_resolve_ref(root, str(relative)))
    return current


def _issue(stage: str, code: str, message: str, kind: str) -> dict[str, str]:
    return {"stage": stage, "code": code, "message": message, "kind": kind}


def stage_status(root: Path | str, *, target_stage: str | None = None) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    if target_stage is not None and target_stage not in STAGE_ORDER:
        raise StageGateError(f"unknown stage: {target_stage}")
    through = (
        STAGE_ORDER if target_stage is None else STAGE_ORDER[: STAGE_ORDER.index(target_stage) + 1]
    )
    ledger = read_stage_locks(base)
    rigor = _rigor(base)
    issues: list[dict[str, str]] = []
    stages: list[dict[str, Any]] = []

    for stage in through:
        lock = (ledger.get("locks") or {}).get(stage)
        kind = _stage_kind(stage)
        if not isinstance(lock, dict):
            issue = _issue(stage, "STAGE_LOCK_MISSING", "current stage lock is missing", kind)
            issues.append(issue)
            stages.append({"stage": stage, "locked": False, "current": False, "kind": kind})
            continue
        try:
            current_hashes = _current_hashes(base, lock)
        except StageGateError as exc:
            current_hashes = {}
            issues.append(_issue(stage, "STAGE_SOURCE_MISSING", str(exc), "source"))
        current = current_hashes == lock.get("input_hashes")
        approval = _approval_for_id(base, str(lock.get("approval_id") or ""))
        approval_ok = bool(
            approval
            and approval.get("revoked") is not True
            and approval.get("project_binding_current") is True
            and approval.get("ledger_integrity_current") is True
            and approval.get("approver_type") in HUMAN_APPROVER_TYPES
            and approval.get("scope") == f"stage:{stage}"
            and approval.get("approval_type") == "stage_lock"
            and approval_is_current(approval, current_hashes)["ok"]
        )
        lock_hash_ok = lock.get("lock_sha256") == stable_content_hash(
            {key: value for key, value in lock.items() if key != "lock_sha256"}
        )
        if not current:
            issues.append(
                _issue(stage, "STAGE_INPUT_STALE", "stage inputs changed after approval", "hash")
            )
        if not approval_ok:
            issues.append(
                _issue(
                    stage,
                    "HUMAN_APPROVAL_MISSING",
                    "current hash-bound human approval is missing",
                    "integrity",
                )
            )
        if not lock_hash_ok:
            issues.append(
                _issue(stage, "STAGE_LOCK_TAMPERED", "stage lock digest is stale", "integrity")
            )
        stages.append(
            {
                "stage": stage,
                "locked": True,
                "current": current and approval_ok and lock_hash_ok,
                "kind": kind,
                "approval_id": lock.get("approval_id"),
            }
        )

    if rigor == "professional":
        blocking, warnings = issues, []
    elif rigor == "guided":
        blocking = [item for item in issues if item["kind"] != "art"]
        warnings = [item for item in issues if item["kind"] == "art"]
    else:
        blocking, warnings = [], issues
    return {
        "ok": not blocking,
        "kind": "director-stage-status",
        "rigor": rigor,
        "target_stage": target_stage,
        "stages": stages,
        "blocking": blocking,
        "warnings": warnings,
        "next_stage": next(
            (item["stage"] for item in stages if not item["current"]),
            STAGE_ORDER[len(through)] if len(through) < len(STAGE_ORDER) else None,
        ),
    }


def lock_stage(
    root: Path | str,
    *,
    stage: str,
    approval_id: str,
    input_refs: Mapping[str, str] | None = None,
    input_hashes: Mapping[str, str] | None = None,
    enforce_order: bool = True,
) -> dict[str, Any]:
    if stage not in STAGE_ORDER:
        raise StageGateError(f"unknown stage: {stage}")
    base = Path(root).expanduser().resolve()
    rigor = _rigor(base)
    if rigor == "professional" and not input_refs:
        raise StageGateError("professional stage locks require resolvable input refs")
    if stage in PAID_STAGES and not input_refs:
        raise StageGateError("paid stage locks require resolvable input refs")
    hashes = dict(input_hashes or {})
    if input_refs:
        for name, digest in hash_input_refs(base, input_refs).items():
            if name in hashes and hashes[name] != digest:
                raise StageGateError(f"provided hash does not match input ref: {name}")
            hashes[name] = digest
    if not hashes:
        raise StageGateError("stage lock requires exact input hashes")
    approval = _validate_approval(base, stage=stage, approval_id=approval_id, input_hashes=hashes)
    if (enforce_order or rigor == "professional") and STAGE_ORDER.index(stage):
        previous = STAGE_ORDER[STAGE_ORDER.index(stage) - 1]
        prior = stage_status(base, target_stage=previous)
        if not prior["ok"]:
            raise StageGateError(f"prior stage gates are not satisfied before {stage}")

    ledger = read_stage_locks(base)
    event = {
        "stage": stage,
        "input_refs": dict(input_refs or {}),
        "input_hashes": dict(sorted(hashes.items())),
        "approval_id": approval_id,
        "approved_at": approval.get("approved_at"),
        "approver": approval.get("approver"),
        "approver_type": approval.get("approver_type"),
    }
    event["lock_sha256"] = stable_content_hash(event)
    ledger["events"].append(dict(event))
    ledger["locks"][stage] = event
    ledger["revision"] = int(ledger.get("revision") or 0) + 1
    ledger["content_sha256"] = stable_content_hash(ledger)
    write_json(_ledger_path(base), ledger)
    return event
