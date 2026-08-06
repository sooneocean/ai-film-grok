#!/usr/bin/env python3
"""Exact EDL/timeline/shot-set picture lock and post-lock impact."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from approval_ledger import approval_is_current, read_approval_ledger
from director_stage_gates import hash_input_refs, lock_stage
from production_book import stable_content_hash
from util import read_json, write_json

PICTURE_LOCK_PATH = Path("receipts/picture-lock.json")
POST_STALE_PATH = Path("receipts/post-lock-staleness.json")
POST_LOCKS = ("sound", "music", "captions", "mix", "master")


class PictureLockError(ValueError):
    """Picture-lock evidence is incomplete, stale, or non-human."""


def _path(root: Path | str, relative: Path) -> Path:
    return Path(root).expanduser().resolve() / relative


def _normalize_shots(shot_ids: list[str]) -> list[str]:
    shots = [str(item).strip() for item in shot_ids]
    if not shots or any(not item for item in shots):
        raise PictureLockError("picture lock requires exact non-empty shot IDs")
    if len(shots) != len(set(shots)):
        raise PictureLockError("picture lock shot IDs must be unique")
    return shots


def picture_lock_inputs(
    root: Path | str, input_refs: Mapping[str, str], shot_ids: list[str]
) -> dict[str, str]:
    refs = dict(input_refs)
    if "edl" not in refs and "timeline" not in refs:
        raise PictureLockError("picture lock requires an EDL or timeline")
    hashes = hash_input_refs(root, refs)
    hashes["shot_set"] = stable_content_hash(_normalize_shots(shot_ids))
    return dict(sorted(hashes.items()))


def _approval(root: Path | str, approval_id: str, hashes: Mapping[str, str]) -> dict[str, Any]:
    approval = next(
        (
            item
            for item in read_approval_ledger(root).get("approvals") or []
            if item.get("approval_id") == approval_id
        ),
        None,
    )
    if (
        not approval
        or approval.get("revoked") is True
        or approval.get("project_binding_current") is not True
        or approval.get("ledger_integrity_current") is not True
        or approval.get("approver_type") not in {"human", "user"}
        or approval.get("scope") != "stage:picture_lock"
        or approval.get("approval_type") != "stage_lock"
        or not approval_is_current(approval, hashes)["ok"]
    ):
        raise PictureLockError("picture lock requires current hash-bound human approval")
    return approval


def bind_picture_lock(
    root: Path | str,
    *,
    input_refs: Mapping[str, str],
    shot_ids: list[str],
    approval_id: str,
) -> dict[str, Any]:
    shots = _normalize_shots(shot_ids)
    hashes = picture_lock_inputs(root, input_refs, shots)
    approval = _approval(root, approval_id, hashes)
    lock: dict[str, Any] = {
        "schema_version": 1,
        "kind": "picture-lock",
        "input_refs": dict(input_refs),
        "input_hashes": hashes,
        "shot_ids": shots,
        "shot_count": len(shots),
        "approval_id": approval_id,
        "approved_at": approval.get("approved_at"),
        "approver": approval.get("approver"),
        "approver_type": approval.get("approver_type"),
    }
    lock["lock_sha256"] = stable_content_hash(lock)
    write_json(_path(root, PICTURE_LOCK_PATH), lock)
    lock_stage(
        root,
        stage="picture_lock",
        input_refs=input_refs,
        input_hashes={"shot_set": hashes["shot_set"]},
        approval_id=approval_id,
        enforce_order=False,
    )
    return lock


def picture_lock_status(
    root: Path | str, *, current_shot_ids: list[str] | None = None
) -> dict[str, Any]:
    lock = read_json(_path(root, PICTURE_LOCK_PATH))
    if not isinstance(lock, dict):
        return {
            "ok": False,
            "kind": "picture-lock-status",
            "code": "PICTURE_LOCK_MISSING",
            "changed_inputs": [],
            "affected_locks": list(POST_LOCKS),
            "assets_deleted": [],
        }
    supplied_shots = (
        list(lock.get("shot_ids") or []) if current_shot_ids is None else current_shot_ids
    )
    try:
        shots = _normalize_shots(supplied_shots)
        current = picture_lock_inputs(root, lock.get("input_refs") or {}, shots)
    except ValueError:
        shots = [str(item) for item in supplied_shots]
        current = {}
    recorded = dict(lock.get("input_hashes") or {})
    changed = [name for name in recorded if current.get(name) != recorded[name]]
    shot_changed = current.get("shot_set") != recorded.get("shot_set")
    approval = next(
        (
            item
            for item in read_approval_ledger(root).get("approvals") or []
            if item.get("approval_id") == lock.get("approval_id")
        ),
        None,
    )
    approval_current = bool(
        approval
        and approval.get("revoked") is not True
        and approval.get("project_binding_current") is True
        and approval.get("ledger_integrity_current") is True
        and approval.get("approver_type") in {"human", "user"}
        and approval_is_current(approval, current)["ok"]
    )
    lock_hash_ok = lock.get("lock_sha256") == stable_content_hash(
        {key: value for key, value in lock.items() if key != "lock_sha256"}
    )
    ok = not changed and approval_current and lock_hash_ok
    return {
        "ok": ok,
        "kind": "picture-lock-status",
        "changed_inputs": changed,
        "approval_current": approval_current,
        "lock_hash_current": lock_hash_ok,
        "shot_set": {
            "changed": shot_changed,
            "same_count": len(shots) == int(lock.get("shot_count") or 0),
            "locked_ids": list(lock.get("shot_ids") or []),
            "current_ids": shots,
        },
        "affected_locks": list(POST_LOCKS) if changed else [],
        "assets_deleted": [],
    }


def invalidate_post_locks(root: Path | str, *, reason: str) -> dict[str, Any]:
    report = picture_lock_status(root)
    if report["ok"]:
        return {
            "ok": True,
            "changed_inputs": [],
            "affected_locks": [],
            "assets_deleted": [],
        }
    path = _path(root, POST_STALE_PATH)
    ledger = read_json(path) or {
        "schema_version": 1,
        "kind": "post-lock-staleness",
        "events": [],
    }
    event = {
        "reason": str(reason).strip(),
        "changed_inputs": report["changed_inputs"],
        "affected_locks": report["affected_locks"],
        "assets_deleted": [],
    }
    if not event["reason"]:
        raise PictureLockError("post-lock invalidation requires a reason")
    event["impact_sha256"] = stable_content_hash(event)
    ledger["events"].append(event)
    ledger["current"] = {name: "stale" for name in report["affected_locks"]}
    ledger["content_sha256"] = stable_content_hash(ledger)
    write_json(path, ledger)
    return {"ok": True, **event}
