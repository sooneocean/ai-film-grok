#!/usr/bin/env python3
"""Evidence-backed human review packets for individual motion shots."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from media_qa import analyze_media
from security_policy import minimal_subprocess_env, validate_identifier
from util import read_json, write_json


REVIEW_DIMENSIONS = ("identity", "continuity", "composition", "motion", "narrative")


class ShotReviewError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def review_dir(root: Path) -> Path:
    path = Path(root).expanduser().resolve() / "receipts" / "reviews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def review_receipt_path(root: Path, shot_id: str) -> Path:
    sid = validate_identifier(shot_id, field="shot id")
    return review_dir(root) / f"{sid}.json"


def _parse_evidence(values: list[str] | None, *, duration_sec: float) -> dict[str, dict[str, Any]]:
    parsed: dict[str, dict[str, Any]] = {}
    for raw in values or []:
        try:
            dim_part, rest = str(raw).split("@", 1)
            time_part, note = rest.split(":", 1)
            dim = dim_part.strip().lower()
            timestamp = float(time_part.strip())
        except (TypeError, ValueError):
            raise ShotReviewError("evidence must use dimension@seconds:note") from None
        if dim not in REVIEW_DIMENSIONS:
            raise ShotReviewError(f"unknown review evidence dimension: {dim}")
        if timestamp < 0 or timestamp > duration_sec:
            raise ShotReviewError(f"evidence timestamp for {dim} is outside clip duration")
        if not note.strip():
            raise ShotReviewError(f"evidence note for {dim} is empty")
        if dim in parsed:
            raise ShotReviewError(f"duplicate evidence for {dim}")
        parsed[dim] = {"timestamp_sec": round(timestamp, 3), "note": note.strip()}
    return parsed


def _extract_frames(source: Path, destination: Path, duration_sec: float) -> dict[str, Any]:
    stamps = {"first": 0.0, "middle": round(duration_sec / 2, 3), "last": round(max(0.0, duration_sec - 0.05), 3)}
    frames: dict[str, dict[str, Any]] = {}
    for label, stamp in stamps.items():
        out = destination / f"{source.stem}-{label}.jpg"
        proc = subprocess.run(
            ["ffmpeg", "-y", "-ss", str(stamp), "-i", str(source), "-frames:v", "1", "-q:v", "3", str(out)],
            capture_output=True,
            text=True,
            timeout=90,
            env=minimal_subprocess_env(),
        )
        if proc.returncode != 0 or not out.is_file():
            raise ShotReviewError(f"could not extract {label} review frame: {proc.stderr[:300]}")
        frames[label] = {"timestamp_sec": stamp, "path": str(out), "sha256": _sha256(out)}
    contact = destination / f"{source.stem}-contact.jpg"
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-i", frames["first"]["path"], "-i", frames["middle"]["path"], "-i", frames["last"]["path"],
            "-filter_complex", "hstack=inputs=3", "-frames:v", "1", "-q:v", "3", str(contact),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        env=minimal_subprocess_env(),
    )
    if proc.returncode != 0 or not contact.is_file():
        raise ShotReviewError(f"could not create contact sheet: {proc.stderr[:300]}")
    return {"frames": frames, "contact_sheet": {"path": str(contact), "sha256": _sha256(contact)}}


def create_shot_review(
    root: Path,
    *,
    shot_id: str,
    source: Path,
    reviewer: str,
    notes: str,
    scores: dict[str, int],
    evidence_values: list[str] | None,
    references: list[Path] | None = None,
    approve: bool = False,
) -> dict[str, Any]:
    sid = validate_identifier(shot_id, field="shot id")
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise ShotReviewError(f"review source is missing: {source}")
    if not reviewer.strip() or not notes.strip():
        raise ShotReviewError("reviewer and notes are required")
    qa = analyze_media(source, require_audio=False, require_motion=True)
    duration = float(qa.get("duration_sec") or 0.0)
    normalized_scores: dict[str, int] = {}
    for dim in REVIEW_DIMENSIONS:
        value = scores.get(dim)
        if not isinstance(value, int) or not 1 <= value <= 5:
            raise ShotReviewError(f"score for {dim} must be an integer from 1 to 5")
        normalized_scores[dim] = value
    evidence = _parse_evidence(evidence_values, duration_sec=duration)
    if approve and set(evidence) != set(REVIEW_DIMENSIONS):
        missing = sorted(set(REVIEW_DIMENSIONS) - set(evidence))
        raise ShotReviewError("approved review needs timestamp evidence for: " + ", ".join(missing))
    artifacts = _extract_frames(source, review_dir(root), duration)
    refs = []
    for ref in references or []:
        candidate = Path(ref).expanduser().resolve()
        if candidate.is_file():
            refs.append({"path": str(candidate), "sha256": _sha256(candidate)})
    approved = bool(approve and qa.get("ok") and all(score >= 4 for score in normalized_scores.values()) and len(evidence) == len(REVIEW_DIMENSIONS))
    packet = {
        "schema_version": 2,
        "kind": "shot-review",
        "at": _utc_now(),
        "shot_id": sid,
        "approved": approved,
        "reviewer": reviewer.strip(),
        "notes": notes.strip(),
        "source": {"path": str(source), "sha256": _sha256(source), "bytes": source.stat().st_size},
        "technical_qa": qa,
        "artifacts": artifacts,
        "references": refs,
        "scorecard": {"dimensions": normalized_scores, "pass_threshold": 4, "all_pass": all(score >= 4 for score in normalized_scores.values())},
        "evidence": evidence,
    }
    path = review_receipt_path(root, sid)
    write_json(path, packet)
    packet["path"] = str(path)
    return packet


def approved_review_for_clip(root: Path, *, shot_id: str, clip: Path, receipt: Path | None = None) -> dict[str, Any]:
    path = Path(receipt).expanduser().resolve() if receipt else review_receipt_path(root, shot_id)
    packet = read_json(path)
    if not isinstance(packet, dict):
        raise ShotReviewError(f"approved shot-review receipt is missing: {path}")
    if packet.get("kind") != "shot-review" or packet.get("approved") is not True:
        raise ShotReviewError("shot-review receipt is not approved")
    if packet.get("shot_id") != shot_id:
        raise ShotReviewError("shot-review receipt belongs to another shot")
    source = packet.get("source") if isinstance(packet.get("source"), dict) else {}
    if source.get("sha256") != _sha256(Path(clip).expanduser().resolve()):
        raise ShotReviewError("shot-review receipt source hash does not match clip")
    if set((packet.get("evidence") or {}).keys()) != set(REVIEW_DIMENSIONS):
        raise ShotReviewError("shot-review receipt lacks complete timestamp evidence")
    return {"path": str(path), "sha256": _sha256(path), "reviewed_at": packet.get("at"), "scorecard": packet.get("scorecard")}
