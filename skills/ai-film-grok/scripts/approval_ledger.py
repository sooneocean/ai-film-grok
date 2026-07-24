#!/usr/bin/env python3
"""Unified append-only human approval ledger bound to exact input hashes."""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from production_book import stable_content_hash
from util import exclusive_file_lock, read_json, utc_now, write_json

LEDGER_NAME = "approval-ledger.json"
SCHEMA_VERSION = 1
HUMAN_APPROVER_TYPES = {"human", "user"}
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


class ApprovalValidationError(ValueError):
    """Approval evidence is missing, ambiguous, or non-human."""


class ApprovalLedgerConflict(ApprovalValidationError):
    """Approval-ledger optimistic lock failed."""


def approval_ledger_path(root: Path | str) -> Path:
    candidate = Path(root).expanduser()
    if candidate.name == LEDGER_NAME:
        return candidate
    return candidate / "receipts" / LEDGER_NAME


def _project_binding(path: Path) -> str:
    return stable_content_hash({"project_root": str(path.parent.parent.resolve())})


def new_approval_ledger() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "approval-ledger",
        "revision": 0,
        "approvals": [],
        "revocations": [],
    }


def _ledger_for_write(ledger: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(ledger)
    output.pop("integrity_current", None)
    for approval in output.get("approvals") or []:
        if isinstance(approval, dict):
            approval.pop("revoked", None)
            approval.pop("project_binding_current", None)
            approval.pop("ledger_integrity_current", None)
    output["content_sha256"] = stable_content_hash(output)
    return output


def read_approval_ledger(root: Path | str) -> dict[str, Any]:
    path = approval_ledger_path(root)
    raw = read_json(path)
    if raw is None:
        return new_approval_ledger()
    recorded_hash = raw.get("content_sha256")
    if isinstance(recorded_hash, str) and recorded_hash != stable_content_hash(raw):
        raise ApprovalValidationError("approval ledger content hash is stale or tampered")
    integrity_current = isinstance(recorded_hash, str)
    raw.setdefault("schema_version", SCHEMA_VERSION)
    raw.setdefault("kind", "approval-ledger")
    raw.setdefault("revision", len(raw.get("approvals") or []))
    raw.setdefault("approvals", [])
    raw.setdefault("revocations", [])
    raw["integrity_current"] = integrity_current
    revoked_ids = {
        str(item.get("approval_id"))
        for item in raw["revocations"]
        if isinstance(item, dict) and item.get("approval_id")
    }
    current_project_binding = _project_binding(path)
    for approval in raw["approvals"]:
        if isinstance(approval, dict):
            expected_id = f"approval-{stable_content_hash({key: value for key, value in approval.items() if key not in {'approval_id', 'revoked', 'project_binding_current', 'ledger_integrity_current'}})[:24]}"
            if approval.get("approval_id") != expected_id:
                raise ApprovalValidationError("approval entry id is stale or tampered")
            approval["revoked"] = approval.get("approval_id") in revoked_ids
            approval["project_binding_current"] = (
                approval.get("project_binding") == current_project_binding
            )
            approval["ledger_integrity_current"] = integrity_current
    return raw


def _validate_hashes(input_hashes: Mapping[str, str]) -> dict[str, str]:
    if not input_hashes:
        raise ApprovalValidationError("approval requires exact input hashes")
    hashes = {str(key): str(value).lower() for key, value in input_hashes.items()}
    if any(not key.strip() or not _SHA256_RE.fullmatch(value) for key, value in hashes.items()):
        raise ApprovalValidationError("every approval input must have a named SHA-256 hash")
    return dict(sorted(hashes.items()))


def build_approval(
    *,
    scope: str,
    approval_type: str,
    approver_type: str,
    approver: str,
    input_hashes: Mapping[str, str],
    evidence_refs: list[str],
    transaction_id: str,
    user_phrase: str | None = None,
    authorization_event: str | dict[str, Any] | None = None,
    approved_at: str | None = None,
    project_binding: str | None = None,
) -> dict[str, Any]:
    if approver_type not in HUMAN_APPROVER_TYPES:
        raise ApprovalValidationError("approver_type must be human or user")
    if isinstance(user_phrase, bool) or isinstance(authorization_event, bool):
        raise ApprovalValidationError("boolean approvals are invalid")
    phrase_ok = isinstance(user_phrase, str) and bool(user_phrase.strip())
    event_ok = (isinstance(authorization_event, str) and bool(authorization_event.strip())) or (
        isinstance(authorization_event, dict) and bool(authorization_event)
    )
    if phrase_ok == event_ok:
        raise ApprovalValidationError(
            "approval requires exactly one verbatim user phrase or authorization event"
        )
    if not all(
        isinstance(value, str) and value.strip() for value in (scope, approval_type, approver)
    ):
        raise ApprovalValidationError("scope, approval type, and approver are required")
    if not isinstance(transaction_id, str) or not transaction_id.strip():
        raise ApprovalValidationError("approval requires a transaction id")
    if not evidence_refs or any(
        not isinstance(ref, str) or not ref.strip() for ref in evidence_refs
    ):
        raise ApprovalValidationError("approval requires evidence refs")

    approval: dict[str, Any] = {
        "scope": scope.strip(),
        "approval_type": approval_type.strip(),
        "approver_type": approver_type,
        "approver": approver.strip(),
        "approved_at": approved_at or utc_now(),
        "input_hashes": _validate_hashes(input_hashes),
        "evidence_refs": list(dict.fromkeys(ref.strip() for ref in evidence_refs)),
        "transaction_id": transaction_id.strip(),
        "project_binding": project_binding,
    }
    if phrase_ok:
        approval["user_phrase"] = user_phrase
    else:
        approval["authorization_event"] = copy.deepcopy(authorization_event)
    approval["approval_id"] = f"approval-{stable_content_hash(approval)[:24]}"
    return approval


def append_approval(
    root: Path | str,
    *,
    expected_revision: int | None = None,
    **approval_fields: Any,
) -> dict[str, Any]:
    path = approval_ledger_path(root)
    with exclusive_file_lock(path):
        ledger = read_approval_ledger(path)
        actual_revision = int(ledger.get("revision") or 0)
        if expected_revision is not None and actual_revision != expected_revision:
            raise ApprovalLedgerConflict(
                f"expected revision {expected_revision}, current revision is {actual_revision}"
            )
        approval_fields["project_binding"] = _project_binding(path)
        approval = build_approval(**approval_fields)
        if any(item.get("approval_id") == approval["approval_id"] for item in ledger["approvals"]):
            return approval
        ledger["approvals"].append(approval)
        ledger["revision"] = actual_revision + 1
        ledger["updated_at"] = utc_now()
        ledger = _ledger_for_write(ledger)
        write_json(path, ledger)
        return approval


def approval_is_current(
    approval: Mapping[str, Any], current_input_hashes: Mapping[str, str]
) -> dict[str, Any]:
    recorded = approval.get("input_hashes")
    if not isinstance(recorded, dict) or not recorded:
        return {
            "ok": False,
            "approval_id": approval.get("approval_id"),
            "changed_inputs": [],
            "missing_inputs": [],
            "unexpected_inputs": sorted(str(key) for key in current_input_hashes),
            "reason": "approval has no exact input hashes",
        }
    current = {str(key): str(value).lower() for key, value in current_input_hashes.items()}
    changed = sorted(
        key for key in recorded.keys() & current.keys() if recorded[key] != current[key]
    )
    missing = sorted(recorded.keys() - current.keys())
    unexpected = sorted(current.keys() - recorded.keys())
    ok = not changed and not missing and not unexpected
    return {
        "ok": ok,
        "approval_id": approval.get("approval_id"),
        "changed_inputs": changed,
        "missing_inputs": missing,
        "unexpected_inputs": unexpected,
        "reason": None if ok else "approval inputs are not current",
    }


def find_current_approval(
    ledger: Mapping[str, Any],
    *,
    scope: str,
    approval_type: str,
    current_input_hashes: Mapping[str, str],
) -> dict[str, Any] | None:
    for approval in reversed(list(ledger.get("approvals") or [])):
        if approval.get("revoked") is True:
            continue
        if approval.get("project_binding_current") is not True:
            continue
        if approval.get("ledger_integrity_current") is not True:
            continue
        if approval.get("scope") != scope or approval.get("approval_type") != approval_type:
            continue
        if approval_is_current(approval, current_input_hashes)["ok"]:
            return approval
    return None


def revoke_approval(
    root: Path | str,
    *,
    approval_id: str,
    reason: str,
    authorization_event: str,
    expected_revision: int,
) -> dict[str, Any]:
    path = approval_ledger_path(root)
    with exclusive_file_lock(path):
        ledger = read_approval_ledger(path)
        actual_revision = int(ledger.get("revision") or 0)
        if actual_revision != expected_revision:
            raise ApprovalLedgerConflict(
                f"expected revision {expected_revision}, current revision is {actual_revision}"
            )
        if not any(item.get("approval_id") == approval_id for item in ledger["approvals"]):
            raise ApprovalValidationError("approval to revoke does not exist")
        if not reason.strip() or not authorization_event.strip():
            raise ApprovalValidationError(
                "revocation requires reason and human authorization event"
            )
        event = {
            "approval_id": approval_id,
            "reason": reason.strip(),
            "authorization_event": authorization_event.strip(),
            "revoked_at": utc_now(),
        }
        event["revocation_id"] = f"revocation-{stable_content_hash(event)[:24]}"
        ledger["revocations"].append(event)
        ledger["revision"] = actual_revision + 1
        ledger["updated_at"] = utc_now()
        ledger = _ledger_for_write(ledger)
        write_json(path, ledger)
        return event
