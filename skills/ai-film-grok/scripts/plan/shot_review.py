#!/usr/bin/env python3
"""Evidence-backed human review packets for individual motion shots."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from media.media_qa import analyze_media
from performance_evidence import (
    PerformanceEvidenceError,
    find_shot,
    parse_performance_evidence,
    performance_contract,
    validate_performance_evidence,
)
from security_policy import minimal_subprocess_env, validate_identifier
from util import read_json, utc_now, write_json
from util import sha256_file as _sha256

# Core five always required; coitus optional (act/climax mute-frame when scored)
CORE_REVIEW_DIMENSIONS = (
    "identity",
    "continuity",
    "composition",
    "motion",
    "narrative",
)
OPTIONAL_REVIEW_DIMENSIONS = ("coitus",)  # mute-frame intercourse readability
REVIEW_DIMENSIONS = CORE_REVIEW_DIMENSIONS + OPTIONAL_REVIEW_DIMENSIONS


class ShotReviewError(ValueError):
    pass


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
    stamps = {
        "first": 0.0,
        "middle": round(duration_sec / 2, 3),
        # Seeking to the final decoded frame is fragile for short H.264 clips:
        # ffmpeg can land after the last keyframe and emit nothing.  Keep a
        # small, deterministic safety margin inside the actual media span.
        "last": round(max(0.0, duration_sec - 0.25), 3),
    }
    frames: dict[str, dict[str, Any]] = {}
    for label, stamp in stamps.items():
        out = destination / f"{source.stem}-{label}.jpg"
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(stamp),
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(out),
            ],
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
            "ffmpeg",
            "-y",
            "-i",
            frames["first"]["path"],
            "-i",
            frames["middle"]["path"],
            "-i",
            frames["last"]["path"],
            "-filter_complex",
            "hstack=inputs=3",
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(contact),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        env=minimal_subprocess_env(),
    )
    if proc.returncode != 0 or not contact.is_file():
        raise ShotReviewError(f"could not create contact sheet: {proc.stderr[:300]}")
    return {"frames": frames, "contact_sheet": {"path": str(contact), "sha256": _sha256(contact)}}


def _extract_performance_evidence_frames(
    source: Path, destination: Path, evidence: dict[str, dict[str, Any]]
) -> None:
    """Anchor each human observation to a reviewable frame from this exact clip."""
    for kind, record in evidence.items():
        timestamp = record["timestamp_sec"]
        out = destination / f"{source.stem}-performance-{kind}.jpg"
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(timestamp),
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(out),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            env=minimal_subprocess_env(),
        )
        if proc.returncode != 0 or not out.is_file():
            raise ShotReviewError(
                f"could not extract {kind} performance evidence frame: {proc.stderr[:300]}"
            )
        record["frame"] = {"path": str(out), "sha256": _sha256(out)}


def _continuity_packet(root: Path, shot_id: str, source: Path) -> dict[str, Any]:
    """Bind the review to neighbouring takes without inventing continuity approval."""
    manifest = read_json(Path(root) / "manifest.json") or {}
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    ordered = list(clips)
    try:
        index = ordered.index(shot_id)
    except ValueError:
        index = -1
    neighbours: dict[str, dict[str, Any]] = {}
    for label, neighbour_index in (("previous", index - 1), ("next", index + 1)):
        if neighbour_index < 0 or neighbour_index >= len(ordered):
            continue
        other_id = str(ordered[neighbour_index])
        record = clips.get(other_id)
        if not isinstance(record, dict) or record.get("status") != "approved":
            continue
        other_path = Path(str(record.get("path") or "")).expanduser()
        if other_path.is_file():
            neighbours[label] = {
                "shot_id": other_id,
                "clip_path": str(other_path.resolve()),
                "clip_sha256": _sha256(other_path),
                "quality_evidence_sha256": (record.get("quality_evidence") or {}).get("sha256"),
                "review_sha256": (record.get("shot_review") or {}).get("sha256"),
            }
    style = read_json(Path(root) / "style-bible.json") or {}
    return {
        "ok": True,
        "reviewed_clip_sha256": _sha256(source),
        "neighbours": neighbours,
        "style_lock_sha256": _sha256(Path(root) / "style-bible.json")
        if style.get("locked") is True and (Path(root) / "style-bible.json").is_file()
        else None,
        "note": "Neighbour hashes make continuity approval stale when an adjacent approved take changes.",
    }


def create_shot_review(
    root: Path,
    *,
    shot_id: str,
    source: Path,
    reviewer: str,
    notes: str,
    scores: dict[str, int],
    evidence_values: list[str] | None,
    performance_evidence_values: list[str] | None = None,
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
    for dim in CORE_REVIEW_DIMENSIONS:
        value = scores.get(dim)
        if not isinstance(value, int) or not 1 <= value <= 5:
            raise ShotReviewError(f"score for {dim} must be an integer from 1 to 5")
        normalized_scores[dim] = value
    # Optional coitus (mute-frame) when author provides score
    if "coitus" in scores and scores.get("coitus") is not None:
        value = scores.get("coitus")
        if not isinstance(value, int) or not 1 <= value <= 5:
            raise ShotReviewError("score for coitus must be an integer from 1 to 5")
        normalized_scores["coitus"] = value
    evidence = _parse_evidence(evidence_values, duration_sec=duration)
    shot, performance_required = find_shot(root, sid)
    # max act/climax: Mute Frame coitus score required on approve
    heat_phase = str((shot or {}).get("heat_phase") or "").strip().lower()
    film_heat = ""
    try:
        spec = read_json(Path(root) / "film-spec.json") or {}
        film_heat = str(spec.get("heat_scale") or "").strip().lower()
    except Exception:
        film_heat = ""
    mute_frame_required = film_heat == "max" and heat_phase in {"act", "climax"}
    if mute_frame_required and approve and "coitus" not in normalized_scores:
        raise ShotReviewError(
            "max act/climax approve requires mute-frame coitus score "
            "(--score-coitus 1-5): 静音一帧是否可读办事"
        )
    if mute_frame_required and approve and normalized_scores.get("coitus", 0) < 4:
        raise ShotReviewError(
            "max act/climax mute-frame coitus score must be ≥4 to approve "
            "(hug-only / unreadable union fails Mute Frame Test)"
        )
    contract = performance_contract(shot, required=performance_required)
    try:
        performance_evidence = parse_performance_evidence(
            performance_evidence_values, duration_sec=duration
        )
    except PerformanceEvidenceError as exc:
        raise ShotReviewError(str(exc)) from None
    performance = validate_performance_evidence(contract, performance_evidence)
    required_ev = set(CORE_REVIEW_DIMENSIONS)
    if "coitus" in normalized_scores:
        required_ev.add("coitus")
    if approve and not required_ev.issubset(set(evidence)):
        missing = sorted(required_ev - set(evidence))
        raise ShotReviewError("approved review needs timestamp evidence for: " + ", ".join(missing))
    if approve and not performance["ok"]:
        details = ", ".join(performance["missing"] or performance["codes"])
        raise ShotReviewError("approved review needs performance evidence: " + details)
    artifacts = _extract_frames(source, review_dir(root), duration)
    _extract_performance_evidence_frames(source, review_dir(root), performance_evidence)
    refs = []
    for ref in references or []:
        candidate = Path(ref).expanduser().resolve()
        if candidate.is_file():
            refs.append({"path": str(candidate), "sha256": _sha256(candidate)})
    core_pass = all(normalized_scores[d] >= 4 for d in CORE_REVIEW_DIMENSIONS)
    opt_pass = all(
        normalized_scores[d] >= 4 for d in OPTIONAL_REVIEW_DIMENSIONS if d in normalized_scores
    )
    approved = bool(
        approve
        and qa.get("ok")
        and core_pass
        and opt_pass
        and required_ev.issubset(set(evidence))
        and performance["ok"]
    )
    adult_evidence = None
    if film_heat == "max" and heat_phase in {"act", "climax"}:
        adult_evidence = {
            "kind": "adult-max-shot-evidence",
            "clip_sha256": _sha256(source),
            "coitus_timestamp_sec": (evidence.get("coitus") or {}).get("timestamp_sec"),
            "visual_coverage": ((shot or {}).get("sensory_cues") or {}).get("visual_coverage"),
            "motion_beat": ((shot or {}).get("sensory_cues") or {}).get("motion_beat"),
            "human_review_required": True,
        }
    packet = {
        "schema_version": 5,
        "kind": "shot-review",
        "at": utc_now(),
        "shot_id": sid,
        "approved": approved,
        "reviewer": reviewer.strip(),
        "notes": notes.strip(),
        "source": {"path": str(source), "sha256": _sha256(source), "bytes": source.stat().st_size},
        "technical_qa": qa,
        "artifacts": artifacts,
        "references": refs,
        "scorecard": {
            "dimensions": normalized_scores,
            "pass_threshold": 4,
            "all_pass": all(score >= 4 for score in normalized_scores.values()),
        },
        "evidence": evidence,
        "performance_contract": performance,
        "continuity_packet": _continuity_packet(root, sid, source),
    }
    if adult_evidence is not None:
        packet["adult_performance_evidence"] = adult_evidence
    path = review_receipt_path(root, sid)
    write_json(path, packet)
    packet["path"] = str(path)
    return packet


def approved_review_for_clip(
    root: Path, *, shot_id: str, clip: Path, receipt: Path | None = None
) -> dict[str, Any]:
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
    ev_keys = set((packet.get("evidence") or {}).keys())
    if not set(CORE_REVIEW_DIMENSIONS).issubset(ev_keys):
        raise ShotReviewError("shot-review receipt lacks complete timestamp evidence")
    shot, performance_required = find_shot(root, shot_id)
    if performance_required:
        receipt_contract = packet.get("performance_contract")
        if not isinstance(receipt_contract, dict):
            raise ShotReviewError("shot-review receipt lacks performance evidence contract")
        expected = performance_contract(shot, required=True)
        checked = validate_performance_evidence(expected, receipt_contract.get("evidence") or {})
        if not checked["ok"]:
            raise ShotReviewError("shot-review receipt lacks valid performance evidence")
    continuity = packet.get("continuity_packet")
    if not isinstance(continuity, dict) or continuity.get("ok") is not True:
        raise ShotReviewError("shot-review receipt lacks continuity review packet")
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "reviewed_at": packet.get("at"),
        "scorecard": packet.get("scorecard"),
        "performance_contract": packet.get("performance_contract"),
    }
