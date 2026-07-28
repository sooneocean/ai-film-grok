"""Production-truth checks for film manifests.

Presence of ``manifest.json`` is not provenance.  A manifest becomes eligible
for production only after its schema, source contract, shot bindings and media
checksums are independently verifiable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json, sha256_file, utc_now, write_json

CURRENT_SCHEMA_VERSION = 2


def _record_errors(root: Path, record: object, *, kind: str, shot_id: str) -> list[str]:
    if not isinstance(record, dict):
        return [f"{kind}.{shot_id}: record must be an object"]
    errors: list[str] = []
    if record.get("shot_id") not in {shot_id, None}:
        errors.append(f"{kind}.{shot_id}: shot_id mismatch")
    path = record.get("path")
    if not isinstance(path, str) or not path.strip():
        errors.append(f"{kind}.{shot_id}: missing local path")
    else:
        candidate = (
            (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        )
        if not candidate.is_file() or candidate.is_symlink():
            errors.append(f"{kind}.{shot_id}: local media missing")
        expected = str(record.get("sha256") or "")
        if not expected:
            errors.append(f"{kind}.{shot_id}: missing sha256")
        elif candidate.is_file() and sha256_file(candidate) != expected:
            errors.append(f"{kind}.{shot_id}: sha256 mismatch")
    if not str(record.get("provider") or "").strip():
        errors.append(f"{kind}.{shot_id}: missing provider provenance")
    return errors


def preflight_manifest(root: Path | str, manifest: dict[str, Any]) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    errors: list[str] = []
    if int(manifest.get("schema_version") or 0) != CURRENT_SCHEMA_VERSION:
        errors.append("manifest schema is legacy; run manifest migrate")
    truth = manifest.get("truth_contract")
    if not isinstance(truth, dict):
        errors.append("missing truth_contract")
    else:
        if truth.get("source_of_truth") != "local-contract-and-receipts":
            errors.append("truth_contract source_of_truth is not local-contract-and-receipts")
        contract_path = root / "film-spec.json"
        expected = str(truth.get("contract_sha256") or "")
        if not contract_path.is_file():
            errors.append("film-spec.json missing")
        elif not expected or sha256_file(contract_path) != expected:
            errors.append("truth_contract contract_sha256 is missing or stale")
    for kind in ("stills", "clips"):
        records = manifest.get(kind) or {}
        if not isinstance(records, dict):
            errors.append(f"{kind} must be an object")
            continue
        for shot_id, record in records.items():
            if isinstance(record, dict) and record.get("status") not in {"approved", "completed"}:
                continue
            errors.extend(_record_errors(root, record, kind=kind, shot_id=str(shot_id)))
    return {
        "ok": not errors,
        "schema_version": manifest.get("schema_version"),
        "current_schema_version": CURRENT_SCHEMA_VERSION,
        "errors": errors,
    }


def migrate_manifest(root: Path | str, *, write: bool = False) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    path = root / "manifest.json"
    manifest = read_json(path)
    candidate = dict(manifest)
    candidate["schema_version"] = CURRENT_SCHEMA_VERSION
    candidate["truth_contract"] = {
        "source_of_truth": "local-contract-and-receipts",
        "migrated_from_schema": manifest.get("schema_version"),
        "migrated_at": utc_now(),
        "contract_sha256": sha256_file(root / "film-spec.json")
        if (root / "film-spec.json").is_file()
        else "",
    }
    check = preflight_manifest(root, candidate)
    needs_refresh = candidate != manifest
    result = {
        "ok": check["ok"],
        "changed": False,
        "path": str(path),
        "preflight": check,
        "reason": "already-current" if not needs_refresh else "refreshed-contract",
    }
    if write and check["ok"] and needs_refresh:
        write_json(path, candidate)
        result["changed"] = True
    return result
