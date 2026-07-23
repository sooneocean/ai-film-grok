#!/usr/bin/env python3
"""Durable, content-addressed receipts for recoverable skill execution."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from util import canonical_json_sha256, read_json, sha256_file, write_json

_TX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")


class TransactionConflict(ValueError):
    """A transaction id was reused for different inputs or approved outputs."""


def stable_hash(value: Any) -> str:
    return canonical_json_sha256(value)


def file_hash(path: Path) -> str:
    return sha256_file(path)


def transaction_id(skill_id: str, payload: dict[str, Any]) -> str:
    supplied = payload.get("transactionId") or payload.get("transaction_id")
    if supplied is not None:
        if not isinstance(supplied, str) or not _TX_RE.fullmatch(supplied):
            raise TransactionConflict("transaction id contains unsafe characters")
        return supplied
    return f"tx-{stable_hash({'skill_id': skill_id, 'payload': payload})[:24]}"


def receipt_path(root: Path, transaction: str) -> Path:
    if not _TX_RE.fullmatch(transaction):
        raise TransactionConflict("invalid transaction id")
    return root / "receipts" / "transactions" / f"{transaction}.json"


def load_receipt(root: Path, transaction: str) -> dict[str, Any] | None:
    value = read_json(receipt_path(root, transaction))
    return value if isinstance(value, dict) else None


def begin_receipt(
    root: Path,
    *,
    transaction: str,
    skill_id: str,
    input_hash: str,
    approval_class: str,
    approval_ref: str | None = None,
    approval_input_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    existing = load_receipt(root, transaction)
    if existing is not None:
        if existing.get("skill_id") != skill_id or existing.get("input_hash") != input_hash:
            raise TransactionConflict("transaction id already belongs to different inputs")
        return existing
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    receipt = {
        "schema_version": 1,
        "kind": "skill-transaction",
        "transaction_id": transaction,
        "skill_id": skill_id,
        "input_hash": input_hash,
        "output_hash": None,
        "output_hashes": {},
        "approval_class": approval_class,
        "approval_ref": approval_ref,
        "approval_input_hashes": dict(approval_input_hashes or {}),
        "state": "started",
        "started_at": now,
    }
    write_json(receipt_path(root, transaction), receipt)
    return receipt


def complete_receipt(
    root: Path,
    receipt: dict[str, Any],
    result: dict[str, Any],
    *,
    output_paths: list[Path] | None = None,
) -> dict[str, Any]:
    declared_paths = list(output_paths or [])
    missing = [str(path) for path in declared_paths if not path.is_file()]
    if result.get("ok") is True and missing:
        raise TransactionConflict("declared outputs are missing: " + ", ".join(missing))
    output_hashes = {str(path): file_hash(path) for path in declared_paths if path.is_file()}
    public_result = dict(result)
    output_hash = stable_hash(public_result)
    public_result.update({"output_hash": output_hash, "output_hashes": output_hashes})
    completed = dict(receipt)
    completed.update(
        {
            "state": "completed" if result.get("ok") is True else "failed",
            "output_hash": output_hash,
            "output_hashes": output_hashes,
            "result": public_result,
            "completed_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        }
    )
    write_json(receipt_path(root, str(completed["transaction_id"])), completed)
    return completed


def refuse_approved_output_overwrite(root: Path, payload: dict[str, Any]) -> None:
    approved = payload.get("approvedOutputHashes") or payload.get("approved_output_hashes") or {}
    approved = approved if isinstance(approved, dict) else {}
    protected = dict(approved)
    expected = {str(item) for item in payload.get("expectedOutputs") or []}
    if expected:
        receipt_dir = root / "receipts" / "transactions"
        for path in receipt_dir.glob("*.json") if receipt_dir.is_dir() else ():
            receipt = read_json(path)
            if not isinstance(receipt, dict):
                continue
            is_approved = (
                receipt.get("state") == "approved"
                or receipt.get("approved") is True
                or isinstance(receipt.get("approval_ref"), str)
            )
            if is_approved and isinstance(receipt.get("output_hashes"), dict):
                protected.update(receipt["output_hashes"])
    for raw_path, approved_hash in protected.items():
        path = Path(str(raw_path)).expanduser()
        if not path.is_absolute():
            path = root / path
        mentioned = raw_path in approved or str(raw_path) in expected or str(path) in expected
        if mentioned and path.is_file() and file_hash(path) == approved_hash:
            raise TransactionConflict(f"refusing to overwrite approved output: {path}")
