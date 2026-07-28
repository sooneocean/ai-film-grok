"""Extract final-MP4 evidence frames for every planned shot transition."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from security_policy import minimal_subprocess_env
from transition_ops import (
    TransitionOperationError,
    assert_hyperframes_safe_operations,
    bind_transition_operations_to_timeline,
)
from util import read_json, write_json
from util import sha256_file as _sha256


def _final_path(root: Path) -> Path | None:
    return next(
        (
            root / relative
            for relative in ("out/film_final.mp4", "out/final.mp4", "final.mp4")
            if (root / relative).is_file()
        ),
        None,
    )


def _delivery(root: Path) -> tuple[Path, dict[str, Any]]:
    path = root / "out" / "final-delivery.json"
    report = read_json(path)
    if not isinstance(report, dict):
        raise ValueError("transition-frame-audit requires out/final-delivery.json")
    return path, report


def bound_operations(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Return operations on the final-film clock, including legacy receipts."""
    transition = report.get("transition")
    if not isinstance(transition, dict):
        raise ValueError("final-delivery transition metadata is missing")
    operations = transition.get("operations")
    timeline = transition.get("film_timeline")
    if not isinstance(operations, list) or not isinstance(timeline, dict):
        raise ValueError("final-delivery transition operations or film timeline is missing")
    try:
        bound = bind_transition_operations_to_timeline(operations, film_timeline=timeline)
        assert_hyperframes_safe_operations(bound)
    except TransitionOperationError as exc:
        raise ValueError(f"invalid final-delivery transition operation: {exc}") from exc
    return bound


def review_timestamps(operation: dict[str, Any], *, fps: float, duration_sec: float) -> list[float]:
    """Map declared review-frame offsets to stable final-film timestamps."""
    if fps <= 0 or duration_sec <= 0:
        raise ValueError("final-delivery fps and duration_sec must be positive")
    timeline = operation.get("timeline")
    qa = operation.get("qa")
    if not isinstance(timeline, dict) or not isinstance(qa, dict):
        raise ValueError("transition operation is missing timeline or qa metadata")
    try:
        seam = float(timeline["at_sec"])
        offsets = qa.get("review_frames")
        if not isinstance(offsets, list) or not offsets:
            raise ValueError
        values = [float(offset) for offset in offsets]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("transition operation has invalid review-frame metadata") from exc
    return sorted({round(min(duration_sec, max(0.0, seam + offset / fps)), 3) for offset in values})


def build_transition_frame_audit(root: Path) -> dict[str, Any]:
    """Write review frames for every seam; never treats extraction as approval."""
    root = Path(root).expanduser().resolve()
    final = _final_path(root)
    if final is None:
        raise ValueError("transition-frame-audit requires final MP4")
    delivery_path, delivery = _delivery(root)
    final_hash = _sha256(final)
    if delivery.get("output_sha256") != final_hash:
        raise ValueError("final MP4 no longer matches final-delivery receipt")
    try:
        fps = float(delivery.get("fps"))
        duration_sec = float(delivery.get("duration_sec"))
    except (TypeError, ValueError) as exc:
        raise ValueError("final-delivery requires numeric fps and duration_sec") from exc
    operations = bound_operations(delivery)
    frame_dir = root / "receipts" / "transition-frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    transitions: list[dict[str, Any]] = []
    for operation in operations:
        join_index = int(operation.get("join_index", -1))
        if join_index < 0:
            raise ValueError("transition operation has invalid join_index")
        frames = []
        for frame_index, timestamp in enumerate(
            review_timestamps(operation, fps=fps, duration_sec=duration_sec), 1
        ):
            output = (
                frame_dir / f"join-{join_index:03d}-frame-{frame_index:02d}-{timestamp:.3f}.png"
            )
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-v",
                    "error",
                    "-ss",
                    f"{timestamp:.3f}",
                    "-i",
                    str(final),
                    "-frames:v",
                    "1",
                    str(output),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                env=minimal_subprocess_env(),
            )
            if proc.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
                raise ValueError(f"could not extract transition review frame at {timestamp:.3f}s")
            frames.append(
                {"timestamp_sec": timestamp, "path": str(output), "sha256": _sha256(output)}
            )
        transitions.append(
            {
                "join_id": operation.get("join_id"),
                "join_index": join_index,
                "from_shot": operation.get("from_shot"),
                "to_shot": operation.get("to_shot"),
                "continuity_class": operation.get("continuity_class"),
                "picture": operation.get("picture"),
                "timeline": operation.get("timeline"),
                "frames": frames,
            }
        )
    report = {
        "kind": "transition-frame-audit",
        "schema_version": 1,
        "final": {"path": str(final), "sha256": final_hash},
        "final_delivery": {"path": str(delivery_path), "sha256": _sha256(delivery_path)},
        "fps": fps,
        "duration_sec": duration_sec,
        "transition_count": len(transitions),
        "transitions": transitions,
        "state": "needs_human_transition_review",
        "human_review_prompt": "Inspect every seam sequence for intended continuity, no double image, no subtitle collision, and correct visual handoff.",
    }
    path = root / "receipts" / "transition-frame-audit.json"
    write_json(path, report)
    report["path"] = str(path)
    return report


def transition_frame_audit_fresh(root: Path) -> dict[str, Any]:
    """Check that every reviewed seam still belongs to the current final delivery."""
    root = Path(root).expanduser().resolve()
    audit_path = root / "receipts" / "transition-frame-audit.json"
    audit = read_json(audit_path) or {}
    final = _final_path(root)
    delivery_path = root / "out" / "final-delivery.json"
    current = {
        "final": _sha256(final) if final else None,
        "final_delivery": _sha256(delivery_path) if delivery_path.is_file() else None,
    }
    bound = {
        "final": (audit.get("final") or {}).get("sha256"),
        "final_delivery": (audit.get("final_delivery") or {}).get("sha256"),
    }
    transitions = audit.get("transitions") if isinstance(audit.get("transitions"), list) else []
    frames_ok = bool(audit) and all(
        isinstance(frame, dict)
        and (path := Path(str(frame.get("path") or ""))).is_file()
        and frame.get("sha256") == _sha256(path)
        for transition in transitions
        if isinstance(transition, dict)
        for frame in (
            transition.get("frames") if isinstance(transition.get("frames"), list) else []
        )
    )
    has_all_frames = all(
        isinstance(transition, dict)
        and isinstance(transition.get("frames"), list)
        and bool(transition["frames"])
        for transition in transitions
    )
    stale = (
        not audit
        or current != bound
        or not frames_ok
        or not has_all_frames
        or audit.get("transition_count") != len(transitions)
    )
    return {
        "present": bool(audit),
        "stale": stale,
        "current": current,
        "bound": bound,
        "transition_count": len(transitions),
        "audit_path": str(audit_path) if audit_path.is_file() else None,
    }


def _human_transition_phrase(phrase: str) -> bool:
    text = (phrase or "").strip().lower()
    if not text or any(marker in text for marker in ("不通过", "重做", "reject", "fail")):
        return False
    approved = ("通过", "批准", "approved", "pass")
    subject = ("转场", "镜头", "transition", "seam")
    return any(marker in text for marker in approved) and any(marker in text for marker in subject)


def attest_transition_review(root: Path, *, user_phrase: str) -> dict[str, Any]:
    """Record explicit human approval only for a complete, current seam audit."""
    root = Path(root).expanduser().resolve()
    freshness = transition_frame_audit_fresh(root)
    audit_path = root / "receipts" / "transition-frame-audit.json"
    audit = read_json(audit_path) or {}
    if not freshness["present"] or freshness["stale"]:
        raise ValueError("transition-frame audit is missing, incomplete, or stale")
    if not _human_transition_phrase(user_phrase):
        raise ValueError(
            "transition attestation requires an explicit human transition approval phrase"
        )
    attestation = {
        "kind": "transition-frame-attestation",
        "schema_version": 1,
        "audit_path": str(audit_path),
        "audit_sha256": _sha256(audit_path),
        "final": audit["final"],
        "final_delivery": audit["final_delivery"],
        "transition_count": audit["transition_count"],
        "user_phrase": user_phrase.strip(),
        "all_seams_reviewed": True,
        "state": "human_transition_review_approved",
    }
    path = root / "receipts" / "transition-frame-attestation.json"
    write_json(path, attestation)
    attestation["path"] = str(path)
    return attestation


def transition_review_evidence_status(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    audit = transition_frame_audit_fresh(root)
    attestation_path = root / "receipts" / "transition-frame-attestation.json"
    attestation = read_json(attestation_path) or {}
    approved = (
        audit["present"]
        and not audit["stale"]
        and attestation.get("kind") == "transition-frame-attestation"
        and attestation.get("state") == "human_transition_review_approved"
        and attestation.get("all_seams_reviewed") is True
        and attestation.get("transition_count") == audit["transition_count"]
        and attestation.get("audit_sha256")
        == _sha256(root / "receipts" / "transition-frame-audit.json")
        and (attestation.get("final") or {}).get("sha256") == audit["current"]["final"]
        and (attestation.get("final_delivery") or {}).get("sha256")
        == audit["current"]["final_delivery"]
    )
    return {
        "ok": approved,
        "audit": audit,
        "attestation_path": str(attestation_path) if attestation_path.is_file() else None,
    }
