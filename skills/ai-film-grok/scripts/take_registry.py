"""Hash-bound take history and active-take selection for one shot."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from util import sha256_file, utc_now, write_json


def take_id(shot_id: str, sha256: str) -> str:
    """Return a stable, human-readable identity for a media take."""
    return f"{shot_id}--{sha256[:12]}"


def archive_active_clip(
    root: Path, shot_id: str, manifest: dict[str, Any]
) -> dict[str, Any] | None:
    """Copy the current active clip aside before register-clip replaces its path."""
    current = (manifest.get("clips") or {}).get(shot_id)
    if not isinstance(current, dict):
        return None
    source = Path(str(current.get("path") or ""))
    if not source.is_file():
        return None
    digest = str(current.get("sha256") or sha256_file(source))
    archive_dir = Path(root).expanduser().resolve() / "clips" / "takes"
    archive_dir.mkdir(parents=True, exist_ok=True)
    destination = archive_dir / f"{take_id(shot_id, digest)}{source.suffix.lower()}"
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    archived = dict(current)
    archived.update(
        {
            "take_id": take_id(shot_id, digest),
            "state": "superseded",
            "archived_path": str(destination),
            "archived_at": utc_now(),
        }
    )
    return archived


def register_active_take(
    root: Path,
    manifest: dict[str, Any],
    record: dict[str, Any],
    *,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach take identity and preserve prior evidence without deleting it."""
    sid = str(record.get("shot_id") or "")
    digest = str(record.get("sha256") or "")
    if not sid or not digest:
        raise ValueError("active take requires shot_id and sha256")
    current = dict(record)
    current["take_id"] = take_id(sid, digest)
    current["state"] = "active"
    current["active"] = True
    if previous:
        history = manifest.setdefault("take_history", {}).setdefault(sid, [])
        history.append(previous)
    manifest.setdefault("active_takes", {})[sid] = current["take_id"]
    manifest.setdefault("clips", {})[sid] = current
    receipt = {
        "schema_version": 1,
        "kind": "active-take-selection",
        "shot_id": sid,
        "active_take_id": current["take_id"],
        "active_sha256": digest,
        "previous_take_id": previous.get("take_id") if previous else None,
        "at": utc_now(),
    }
    receipt_path = Path(root).expanduser().resolve() / "receipts" / "takes" / f"{sid}.json"
    write_json(receipt_path, receipt)
    current["active_take_receipt"] = str(receipt_path)
    return current


def mark_shots_stale(
    root: Path,
    manifest: dict[str, Any],
    shot_ids: list[str],
    *,
    reason: str,
) -> dict[str, Any]:
    """Mark only affected active takes stale while retaining their media."""
    changed: list[str] = []
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    for sid in shot_ids:
        record = clips.get(sid)
        if not isinstance(record, dict):
            continue
        record["state"] = "stale"
        record["active"] = False
        record["stale_reason"] = reason
        changed.append(sid)
    return {"ok": True, "changed_shots": changed, "reason": reason}


def compare_takes(manifest: dict[str, Any], shot_id: str) -> dict[str, Any]:
    """Return active and superseded takes in a stable comparison order."""
    current = (manifest.get("clips") or {}).get(shot_id)
    history = (manifest.get("take_history") or {}).get(shot_id) or []
    candidates = [item for item in [current, *history] if isinstance(item, dict)]
    rows = []
    for item in candidates:
        quality = item.get("quality_gate") if isinstance(item.get("quality_gate"), dict) else {}
        review = quality.get("review") if isinstance(quality.get("review"), dict) else {}
        dimensions = (review.get("scorecard") or {}).get("dimensions") or {}
        rows.append(
            {
                "take_id": item.get("take_id"),
                "sha256": item.get("sha256"),
                "state": item.get("state"),
                "active": item.get("active") is True,
                "quality_ok": quality.get("ok") is True,
                "review_approved": review.get("approved") is True,
                "score_total": sum(int(value or 0) for value in dimensions.values()),
            }
        )
    rows.sort(key=lambda item: (not item["active"], -item["score_total"], str(item["take_id"])))
    return {"shot_id": shot_id, "candidate_count": len(rows), "candidates": rows}
