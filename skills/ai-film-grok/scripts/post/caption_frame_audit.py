"""Extract deterministic final-MP4 frames during subtitle cues for human post review."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from security_policy import minimal_subprocess_env
from subtitle_dialogue_alignment import _cues
from util import read_json, write_json
from util import sha256_file as _sha256


def _first_file(root: Path, *relative: str) -> Path | None:
    return next((root / item for item in relative if (root / item).is_file()), None)


def sample_cue_indices(count: int, *, max_frames: int = 5) -> list[int]:
    if count <= 0 or max_frames < 1:
        return []
    selected = min(count, max_frames)
    if selected == 1:
        return [0]
    return sorted({round(index * (count - 1) / (selected - 1)) for index in range(selected)})


def build_caption_frame_audit(root: Path, *, max_frames: int = 5) -> dict[str, Any]:
    """Write sampled frames; the receipt deliberately remains human-review pending."""
    if max_frames < 1:
        raise ValueError("max_frames must be positive")
    root = Path(root).expanduser().resolve()
    final = _first_file(root, "out/film_final.mp4", "out/final.mp4", "final.mp4")
    srt = _first_file(root, "out/final.srt", "final.srt")
    if final is None or srt is None:
        raise ValueError("caption-frame-audit requires final MP4 and final SRT")
    cues = _cues(srt)
    if not cues:
        raise ValueError("caption-frame-audit requires at least one valid subtitle cue")
    frame_dir = root / "receipts" / "caption-frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    for output_index, cue_index in enumerate(
        sample_cue_indices(len(cues), max_frames=max_frames), 1
    ):
        start, end = cues[cue_index]
        offset = min(max(0.05, (end - start) / 2), max(0.0, end - start - 0.01))
        timestamp = round(start + offset, 3)
        output = frame_dir / f"caption-{output_index:02d}-{timestamp:.3f}.png"
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
            raise ValueError(f"could not extract caption review frame at {timestamp:.3f}s")
        frames.append(
            {
                "cue_index": cue_index,
                "cue_start_sec": start,
                "cue_end_sec": end,
                "timestamp_sec": timestamp,
                "path": str(output),
                "sha256": _sha256(output),
            }
        )
    report = {
        "kind": "caption-frame-audit",
        "schema_version": 1,
        "final": {"path": str(final), "sha256": _sha256(final)},
        "subtitles": {"path": str(srt), "sha256": _sha256(srt), "cue_count": len(cues)},
        "frames": frames,
        "state": "needs_human_readability_review",
        "human_review_prompt": "Inspect every sampled frame for burned subtitle visibility, safe-area clearance, and readable phrase layout.",
    }
    path = root / "receipts" / "caption-frame-audit.json"
    write_json(path, report)
    report["path"] = str(path)
    return report


def select_best_canary_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Select highest-scoring Canary candidate based on status, QA audit, and file size."""
    if not candidates:
        raise ValueError("candidates list cannot be empty")

    def score(cand: dict[str, Any]) -> float:
        s = 0.0
        if cand.get("status") == "succeeded":
            s += 100.0
        if not cand.get("is_canary"):
            # Prefer primary candidate slightly if both succeeded
            s += 5.0
        s += min(float(cand.get("qa_score") or 0.0), 50.0)
        s += min(float(cand.get("file_size_kb") or 0.0) / 100.0, 10.0)
        return s

    return max(candidates, key=score)


def caption_frame_audit_fresh(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    report = read_json(root / "receipts" / "caption-frame-audit.json") or {}
    final = _first_file(root, "out/film_final.mp4", "out/final.mp4", "final.mp4")
    srt = _first_file(root, "out/final.srt", "final.srt")
    current = {
        "final": _sha256(final) if final else None,
        "subtitles": _sha256(srt) if srt else None,
    }
    bound = {
        "final": (report.get("final") or {}).get("sha256"),
        "subtitles": (report.get("subtitles") or {}).get("sha256"),
    }
    stale = not report or any(current[key] != bound[key] for key in current)
    return {"present": bool(report), "stale": stale, "current": current, "bound": bound}


def _human_readability_phrase(phrase: str) -> bool:
    text = (phrase or "").strip().lower()
    if not text or any(marker in text for marker in ("不清楚", "遮挡", "重做", "不通过", "reject")):
        return False
    return any(marker in text for marker in ("字幕", "caption", "可读", "清楚", "通过", "approved"))


def attest_caption_readability(root: Path, *, user_phrase: str) -> dict[str, Any]:
    """Record a human caption-readability decision against current sampled frames."""
    root = Path(root).expanduser().resolve()
    freshness = caption_frame_audit_fresh(root)
    audit_path = root / "receipts" / "caption-frame-audit.json"
    audit = read_json(audit_path) or {}
    if not freshness["present"] or freshness["stale"] or not isinstance(audit.get("frames"), list):
        raise ValueError("caption-frame audit is missing or stale")
    if not _human_readability_phrase(user_phrase):
        raise ValueError(
            "caption attestation requires an explicit human readability approval phrase"
        )
    for frame in audit["frames"]:
        path = Path(str(frame.get("path") or ""))
        if not path.is_file() or frame.get("sha256") != _sha256(path):
            raise ValueError("caption-frame audit contains missing or changed frame evidence")
    attestation = {
        "kind": "caption-frame-attestation",
        "schema_version": 1,
        "audit_path": str(audit_path),
        "audit_sha256": _sha256(audit_path),
        "final": audit["final"],
        "subtitles": audit["subtitles"],
        "frame_count": len(audit["frames"]),
        "user_phrase": user_phrase.strip(),
        "human_readable": True,
        "safe_area_clear": True,
        "unobscured": True,
        "state": "human_readability_approved",
    }
    path = root / "receipts" / "caption-frame-attestation.json"
    write_json(path, attestation)
    attestation["path"] = str(path)
    return attestation


def caption_readability_evidence_status(root: Path) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    audit = caption_frame_audit_fresh(root)
    attestation_path = root / "receipts" / "caption-frame-attestation.json"
    attestation = read_json(attestation_path) or {}
    required = ("human_readable", "safe_area_clear", "unobscured")
    current = audit["current"]
    attested = (
        audit["present"]
        and not audit["stale"]
        and attestation.get("kind") == "caption-frame-attestation"
        and attestation.get("state") == "human_readability_approved"
        and all(attestation.get(field) is True for field in required)
        and (attestation.get("final") or {}).get("sha256") == current["final"]
        and (attestation.get("subtitles") or {}).get("sha256") == current["subtitles"]
        and attestation.get("audit_sha256")
        == _sha256(root / "receipts" / "caption-frame-audit.json")
    )
    return {
        "ok": attested,
        "audit": audit,
        "attestation_path": str(attestation_path) if attestation_path.is_file() else None,
    }
