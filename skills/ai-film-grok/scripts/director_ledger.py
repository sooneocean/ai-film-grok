#!/usr/bin/env python3
"""One checksum-bound ledger for human-authorized production exceptions."""

import hashlib
from pathlib import Path
from typing import Any

from util import read_json, write_json


def _hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_director_ledger(root: Path, *, write: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    spec_path, graph_path = root / "film-spec.json", root / "drama-graph.json"
    spec, manifest = read_json(spec_path) or {}, read_json(root / "manifest.json") or {}
    final = (manifest.get("outputs") or {}).get("final_film") or {}
    carry = (
        spec.get("subtitle_carryovers") if isinstance(spec.get("subtitle_carryovers"), list) else []
    )
    exceptions = [
        item for item in carry if isinstance(item, dict) and item.get("human_approved") is True
    ]
    pending = [
        item
        for item in exceptions
        if not all(
            str(item.get(field) or "").strip()
            for field in ("approved_by", "approved_at", "review_clip")
        )
    ]
    report = {
        "schema_version": 1,
        "kind": "director-approval-ledger",
        "required": bool(exceptions),
        "ok": not pending,
        "exceptions": {"subtitle_carryovers": exceptions},
        "bindings": {
            "film_spec_sha256": _hash(spec_path),
            "drama_graph_sha256": _hash(graph_path),
            "final_mp4_sha256": final.get("sha256"),
        },
        "pending_reapproval": pending,
        "note": "Any binding change invalidates authorization; legacy exceptions need approver, time, and reviewed clip before final approval.",
    }
    if write:
        path = root / "receipts" / "director-approval-ledger.json"
        write_json(path, report)
        report["path"] = str(path)
        report["sha256"] = _hash(path)
    return report


def ledger_is_current(root: Path, ledger: dict[str, Any]) -> bool:
    current = build_director_ledger(root, write=False)
    return ledger.get("bindings") == current.get("bindings")
