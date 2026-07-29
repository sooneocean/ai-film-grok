#!/usr/bin/env python3
"""Atomic CLI operations for independently versioned department bibles."""

from __future__ import annotations

import copy
import difflib
import json
from pathlib import Path
from typing import Any

from approval_ledger import approval_is_current, read_approval_ledger
from department_contracts import (
    migrate_audio_bible,
    migrate_post_bible,
    migrate_style_bible,
    stable_hash,
)
from production_book import read_production_book, update_department
from util import exclusive_file_lock, read_json, write_json

DEPARTMENT_FILES = {
    "visual": "style-bible.json",
    "audio": "audio-bible.json",
    "sound": "audio-bible.json",
    "post": "post-bible.json",
}
_CANONICAL_DEPARTMENTS = {"visual", "audio", "post"}
_BOOK_PATH_KEYS = {
    "visual": ("visual", "style-bible"),
    "audio": ("sound", "audio", "audio-bible"),
    "post": ("post", "post-bible"),
}

# A handoff names the department that may start work next.  It is deliberately
# read-only: ownership changes only through the existing human-approved locks.
_HANDOFFS = {
    "visual": {
        "owner": "visual",
        "inputs": (),
        "produces": ("style-bible.json", "shot visual direction"),
    },
    "audio": {
        "owner": "audio",
        "inputs": (),
        "produces": ("audio-bible.json", "dialogue, music, and mix direction"),
    },
    "post": {
        "owner": "post",
        "inputs": ("visual", "audio"),
        "produces": ("post-bible.json", "editorial and finishing instructions"),
    },
}


class DepartmentCliError(ValueError):
    """A department mutation was invalid or raced another writer."""


def department_path(root: Path | str, department: str) -> Path:
    if department not in DEPARTMENT_FILES:
        raise DepartmentCliError(f"unknown department: {department}")
    base = Path(root).expanduser().resolve()
    canonical = _canonical_department(department)
    try:
        book = read_production_book(base)
    except FileNotFoundError:
        book = {}
    records = book.get("departments") if isinstance(book, dict) else {}
    records = records if isinstance(records, dict) else {}
    for key in _BOOK_PATH_KEYS[canonical]:
        record = records.get(key)
        source_file = record.get("source_file") if isinstance(record, dict) else None
        if not isinstance(source_file, str) or not source_file.strip():
            continue
        candidate = Path(source_file).expanduser()
        candidate = candidate if candidate.is_absolute() else base / candidate
        candidate = candidate.resolve()
        if candidate.is_relative_to(base):
            return candidate
    return (base / DEPARTMENT_FILES[department]).resolve()


def _canonical_department(department: str) -> str:
    return "audio" if department == "sound" else department


def _book_department(department: str) -> str:
    return "sound" if _canonical_department(department) == "audio" else department


def _department_hash(value: dict[str, Any]) -> str:
    return stable_hash(
        {
            key: item
            for key, item in value.items()
            if key not in {"hash", "revision", "state", "approval_ref", "stale_reasons"}
        }
    )


def _legacy_department_hash(value: dict[str, Any]) -> str:
    return stable_hash(
        {
            "kind": value.get("kind"),
            "revision": value.get("revision"),
            "nodes": value.get("nodes"),
        }
    )


def sync_department_book(root: Path | str, department: str, value: dict[str, Any]) -> None:
    try:
        book = read_production_book(root)
    except FileNotFoundError:
        return
    update_department(
        root,
        _book_department(department),
        revision=int(value.get("revision") or 0),
        content_sha256=str(value["hash"]),
        ref=str(department_path(root, department)),
        state=str(value.get("state") or "review"),
        expected_revision=int(book.get("revision") or 0),
    )


def _read(root: Path | str, department: str) -> dict[str, Any]:
    path = department_path(root, department)
    value = read_json(path)
    if not isinstance(value, dict):
        raise DepartmentCliError(f"missing department bible: {path}")
    value.setdefault("revision", 1)
    value.setdefault("state", "draft")
    value.setdefault("stale_reasons", [])
    computed_hash = _department_hash(value)
    recorded_hash = value.get("hash")
    valid_recorded_hashes = {computed_hash, _legacy_department_hash(value)}
    if isinstance(recorded_hash, str) and recorded_hash not in valid_recorded_hashes:
        raise DepartmentCliError(f"department bible hash is stale or tampered: {path}")
    value["hash"] = computed_hash
    return value


def _validate_revision(value: dict[str, Any], expected_revision: int) -> None:
    actual = int(value.get("revision") or 0)
    if actual != expected_revision:
        raise DepartmentCliError(
            f"expected revision {expected_revision}, current revision is {actual}"
        )


def list_departments(root: Path | str) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    names = sorted(_CANONICAL_DEPARTMENTS)
    items = []
    for name in names:
        path = department_path(base, name)
        if path.is_file():
            value = _read(base, name)
            items.append(
                {
                    "id": name,
                    "path": str(path),
                    "revision": value.get("revision"),
                    "state": value.get("state"),
                    "hash": value["hash"],
                }
            )
    return {"ok": True, "count": len(items), "departments": items}


def show_department(root: Path | str, department: str) -> dict[str, Any]:
    value = _read(root, department)
    return {
        "ok": True,
        "department_id": department,
        "path": str(department_path(root, department)),
        "department": value,
    }


def _has_current_lock_approval(root: Path | str, department: str, value: dict[str, Any]) -> bool:
    approval_ref = value.get("approval_ref")
    if not isinstance(approval_ref, str) or not approval_ref:
        return False
    approval = next(
        (
            item
            for item in read_approval_ledger(root).get("approvals") or []
            if item.get("approval_id") == approval_ref
        ),
        None,
    )
    canonical = _canonical_department(department)
    return bool(
        isinstance(approval, dict)
        and approval.get("revoked") is not True
        and approval.get("project_binding_current") is True
        and approval.get("ledger_integrity_current") is True
        and approval.get("approver_type") in {"human", "user"}
        and approval.get("scope") == f"department:{canonical}"
        and approval.get("approval_type") == "department_lock"
        and approval_is_current(approval, {f"department:{canonical}": value["hash"]}).get("ok")
    )


def handoff_department(root: Path | str, department: str) -> dict[str, Any]:
    """Report whether a department has immutable upstream inputs to begin work.

    The report is an assignment receipt, not a state transition.  A receiving
    department can use it to reject stale, draft, or missing upstream bibles
    before any render or media work starts.
    """
    target = _canonical_department(department)
    contract = _HANDOFFS.get(target)
    if contract is None:
        raise DepartmentCliError(f"unknown handoff department: {department}")

    inputs: list[dict[str, Any]] = []
    blockers: list[dict[str, str]] = []
    for upstream in contract["inputs"]:
        try:
            value = _read(root, upstream)
        except (FileNotFoundError, DepartmentCliError) as exc:
            inputs.append({"id": upstream, "ready": False, "error": str(exc)})
            blockers.append({"id": upstream, "reason": "missing_or_invalid"})
            continue
        state = str(value.get("state") or "draft")
        approval_current = state == "locked" and _has_current_lock_approval(root, upstream, value)
        ready = state == "locked" and approval_current
        inputs.append(
            {
                "id": upstream,
                "ready": ready,
                "revision": value.get("revision"),
                "state": state,
                "hash": value["hash"],
                "approval_ref": value.get("approval_ref"),
                "approval_current": approval_current,
            }
        )
        if not ready:
            reason = f"state_{state}" if state != "locked" else "approval_not_current"
            blockers.append({"id": upstream, "reason": reason})

    fingerprint = stable_hash(
        {
            "to": target,
            "inputs": [
                {key: item.get(key) for key in ("id", "revision", "state", "hash")}
                for item in inputs
            ],
        }
    )
    return {
        "ok": not blockers,
        "action": "handoff",
        "to": target,
        "owner": contract["owner"],
        "inputs": inputs,
        "blocked_by": blockers,
        "produces": list(contract["produces"]),
        "handoff_id": f"department-handoff-{target}-{fingerprint[:20]}",
    }


def _merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(base)
    for key, value in patch.items():
        if key in {"revision", "hash", "approval_ref", "state"}:
            continue
        output[key] = copy.deepcopy(value)
    return output


def edit_department(
    root: Path | str,
    department: str,
    *,
    payload_file: Path | str,
    expected_revision: int,
    dry_run: bool,
) -> dict[str, Any]:
    payload = read_json(Path(payload_file))
    if not isinstance(payload, dict):
        raise DepartmentCliError("--payload-file must contain a JSON object")

    def build_report() -> dict[str, Any]:
        current = _read(root, department)
        _validate_revision(current, expected_revision)
        output = _merge(current, payload)
        output["revision"] = expected_revision + 1
        output["state"] = "review"
        output["approval_ref"] = None
        output["hash"] = _department_hash(output)
        return {
            "ok": True,
            "action": "edit",
            "department_id": department,
            "dry_run": dry_run,
            "expected_revision": expected_revision,
            "department": output,
            "transaction_id": f"department-edit-{output['hash'][:20]}",
        }

    if dry_run:
        return build_report()
    path = department_path(root, department)
    with exclusive_file_lock(path):
        report = build_report()
        write_json(path, report["department"])
        sync_department_book(root, department, report["department"])
        return report


def diff_department(
    root: Path | str, department: str, *, payload_file: Path | str
) -> dict[str, Any]:
    current = _read(root, department)
    payload = read_json(Path(payload_file))
    if not isinstance(payload, dict):
        raise DepartmentCliError("--payload-file must contain a JSON object")
    candidate = _merge(current, payload)
    before = json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    after = json.dumps(candidate, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    return {
        "ok": True,
        "department_id": department,
        "changed": current != candidate,
        "diff": "\n".join(
            difflib.unified_diff(before, after, fromfile="current", tofile="candidate", lineterm="")
        ),
    }


def validate_department(root: Path | str, department: str) -> dict[str, Any]:
    value = _read(root, department)
    errors: list[str] = []
    if int(value.get("revision") or 0) < 1:
        errors.append("revision must be positive")
    if value.get("state") not in {"draft", "review", "locked", "stale"}:
        errors.append("state must be draft|review|locked|stale")
    if value.get("state") == "locked" and not isinstance(value.get("approval_ref"), str):
        errors.append("locked department requires approval_ref")
    return {"ok": not errors, "department_id": department, "errors": errors}


def lock_department(
    root: Path | str,
    department: str,
    *,
    approval_ref: str,
    expected_revision: int,
) -> dict[str, Any]:
    if isinstance(approval_ref, bool) or not isinstance(approval_ref, str) or not approval_ref:
        raise DepartmentCliError("lock requires an exact human approval ref")
    current = _read(root, department)
    _validate_revision(current, expected_revision)
    current_hash = _department_hash(current)
    approval = next(
        (
            item
            for item in read_approval_ledger(root).get("approvals") or []
            if item.get("approval_id") == approval_ref
        ),
        None,
    )
    if (
        not isinstance(approval, dict)
        or approval.get("revoked") is True
        or approval.get("project_binding_current") is not True
        or approval.get("ledger_integrity_current") is not True
        or approval.get("approver_type") not in {"human", "user"}
    ):
        raise DepartmentCliError("approval ref is not a current human approval")
    canonical = _canonical_department(department)
    hashes = {f"department:{canonical}": current_hash}
    if (
        approval.get("scope") != f"department:{canonical}"
        or approval.get("approval_type") != "department_lock"
        or not approval_is_current(approval, hashes).get("ok")
    ):
        raise DepartmentCliError("approval ref is not current for the exact department hash")
    output = copy.deepcopy(current)
    output["state"] = "locked"
    output["approval_ref"] = approval_ref
    output["revision"] = int(current.get("revision") or 0) + 1
    output["hash"] = _department_hash(output)
    write_json(department_path(root, department), output)
    sync_department_book(root, department, output)
    return {"ok": True, "department_id": department, "department": output}


def unlock_department(
    root: Path | str, department: str, *, reason: str, expected_revision: int
) -> dict[str, Any]:
    if not reason.strip():
        raise DepartmentCliError("unlock requires a reason")
    current = _read(root, department)
    _validate_revision(current, expected_revision)
    output = copy.deepcopy(current)
    output["state"] = "review"
    output["approval_ref"] = None
    output["revision"] = int(current.get("revision") or 0) + 1
    output.setdefault("stale_reasons", []).append({"reason": reason})
    output["hash"] = _department_hash(output)
    write_json(department_path(root, department), output)
    sync_department_book(root, department, output)
    return {"ok": True, "department_id": department, "department": output}


def mark_department_stale(
    root: Path | str, department: str, *, reason: str, transaction_id: str
) -> dict[str, Any]:
    if not reason.strip() or not transaction_id.strip():
        raise DepartmentCliError("stale transition requires reason and transaction id")
    current = _read(root, department)
    output = copy.deepcopy(current)
    output["state"] = "stale"
    output["approval_ref"] = None
    output["revision"] = int(current.get("revision") or 0) + 1
    output.setdefault("stale_reasons", []).append(
        {"reason": reason.strip(), "transaction_id": transaction_id.strip()}
    )
    output["hash"] = _department_hash(output)
    write_json(department_path(root, department), output)
    return output


def migrate_department(root: Path | str, department: str) -> dict[str, Any]:
    path = department_path(root, department)
    raw = read_json(path) or {}
    migration = {
        "visual": migrate_style_bible,
        "audio": migrate_audio_bible,
        "sound": migrate_audio_bible,
        "post": migrate_post_bible,
    }.get(department)
    if migration is None:
        raise DepartmentCliError(f"no migration contract for department: {department}")
    output = migration(raw)
    output["hash"] = _department_hash(output)
    write_json(path, output)
    sync_department_book(root, department, output)
    return {"ok": True, "department_id": department, "department": output, "path": str(path)}
