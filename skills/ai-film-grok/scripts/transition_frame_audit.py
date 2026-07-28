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
