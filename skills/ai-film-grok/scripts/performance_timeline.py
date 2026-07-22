#!/usr/bin/env python3
"""Compile approved per-shot performance facts into a film-wide director timeline."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from performance_evidence import find_shot, performance_contract, validate_performance_evidence
from util import read_json, write_json


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _timeline_shots(root: Path) -> list[dict[str, Any]]:
    timeline = read_json(root / "timeline.json") or {}
    rows = timeline.get("shots") if isinstance(timeline.get("shots"), list) else []
    return [row for row in rows if isinstance(row, dict) and str(row.get("id") or "").strip()]


def build_performance_timeline(root: Path, *, write: bool = True) -> dict[str, Any]:
    """Build a checksum-bound event timeline; no automatic acting judgment occurs here."""
    root = Path(root).expanduser().resolve()
    timeline_path = root / "timeline.json"
    cursor = 0.0
    entries: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    required_count = 0
    for row in _timeline_shots(root):
        shot_id = str(row["id"])
        duration = max(0.0, float(row.get("duration_sec") or 0.0))
        shot, required = find_shot(root, shot_id)
        entry: dict[str, Any] = {
            "shot_id": shot_id,
            "start_sec": round(cursor, 3),
            "end_sec": round(cursor + duration, 3),
            "duration_sec": duration,
            "required": required,
        }
        if required:
            required_count += 1
            receipt_path = root / "receipts" / "reviews" / f"{shot_id}.json"
            receipt = read_json(receipt_path) or {}
            if receipt.get("approved") is not True:
                errors.append(
                    {
                        "code": "PERFORMANCE_REVIEW_MISSING",
                        "shot_id": shot_id,
                        "message": "approved shot review with performance facts is missing",
                    }
                )
            else:
                expected = performance_contract(shot, required=True)
                recorded = receipt.get("performance_contract") or {}
                evidence = recorded.get("evidence") if isinstance(recorded, dict) else {}
                checked = validate_performance_evidence(
                    expected, evidence if isinstance(evidence, dict) else {}
                )
                entry["review_receipt"] = {
                    "path": str(receipt_path),
                    "sha256": _sha256(receipt_path),
                    "performance_ok": checked["ok"],
                    "codes": checked["codes"],
                }
                if not checked["ok"]:
                    errors.append(
                        {
                            "code": "PERFORMANCE_CONTRACT_INVALID",
                            "shot_id": shot_id,
                            "message": ", ".join(checked["missing"] or checked["codes"]),
                        }
                    )
                for kind, item in (evidence or {}).items():
                    if not isinstance(item, dict):
                        continue
                    frame = item.get("frame") if isinstance(item.get("frame"), dict) else {}
                    frame_path = Path(str(frame.get("path") or ""))
                    if not frame_path.is_file() or frame.get("sha256") != _sha256(frame_path):
                        errors.append(
                            {
                                "code": "PERFORMANCE_EVIDENCE_FRAME_MISSING",
                                "shot_id": shot_id,
                                "message": f"{kind} evidence frame is missing or stale",
                            }
                        )
                    events.append(
                        {
                            "shot_id": shot_id,
                            "kind": kind,
                            "shot_timestamp_sec": item.get("timestamp_sec"),
                            "film_timestamp_sec": round(
                                cursor + float(item.get("timestamp_sec") or 0), 3
                            ),
                            "note": item.get("note"),
                            "frame": frame,
                        }
                    )
        entries.append(entry)
        cursor += duration
    report = {
        "schema_version": 1,
        "kind": "performance-timeline",
        "required": required_count > 0,
        "ok": not errors,
        "timeline": {"path": str(timeline_path), "sha256": _sha256(timeline_path)},
        "duration_sec": round(cursor, 3),
        "shots": entries,
        "events": sorted(events, key=lambda event: float(event["film_timestamp_sec"])),
        "errors": errors,
        "judgment_source": "human_observation",
        "limitation": "The timeline orders checksum-bound human observations; it does not automatically recognize acting, faces, mouths, or story meaning.",
    }
    if write:
        path = root / "receipts" / "performance-timeline.json"
        write_json(path, report)
        report["path"] = str(path)
        report["sha256"] = _sha256(path)
    return report
