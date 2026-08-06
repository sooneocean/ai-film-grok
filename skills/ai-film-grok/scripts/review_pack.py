"""Build an unapproved, hash-bound local review package for one video."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quality_check_video import QualityCheckError, run_quality_check
from security_policy import safe_workspace_directory, validate_identifier
from shot_review import ShotReviewError, _extract_frames
from util import sha256_file, write_json


class ReviewPackError(ValueError):
    """A review package could not be created safely."""


def _pack_dir(root: Path, pack_id: str) -> Path:
    safe_id = validate_identifier(pack_id, field="review package id")
    parent = root / "receipts" / "review-packs"
    parent.mkdir(parents=True, exist_ok=True)
    return safe_workspace_directory(parent, safe_id, field="review package id")


def ensure_review_pack_available(root: Path | str, *, pack_id: str) -> Path:
    """Refuse a reused package ID before a caller downloads any source media."""
    base = Path(root).expanduser().resolve()
    destination = _pack_dir(base, pack_id)
    if destination.exists():
        raise ReviewPackError(f"review package already exists: {destination}")
    return destination


def comfy_download_target(root: Path | str, *, pack_id: str, filename: str) -> Path:
    """Return a root-contained download path before any remote request is made."""
    base = Path(root).expanduser().resolve()
    safe_id = validate_identifier(pack_id, field="review package id")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".mp4", ".mov", ".mkv", ".webm"}:
        raise ReviewPackError("Comfy review download must name a supported video file")
    target = base / "receipts" / "review-inputs" / f"{safe_id}{suffix}"
    if target.exists():
        raise ReviewPackError(f"review download input already exists: {target}")
    return target


def _hash_artifact(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def build_review_pack(
    root: Path | str,
    *,
    pack_id: str,
    source: Path | str,
    expect_audio: bool = True,
    download: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate technical evidence only; this never approves or registers media."""
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise ReviewPackError(f"film root is missing: {base}")
    destination = ensure_review_pack_available(base, pack_id=pack_id)
    candidate = Path(source).expanduser().resolve()
    if not candidate.is_file() or candidate.stat().st_size == 0:
        raise ReviewPackError(f"review source is missing or empty: {candidate}")

    destination.mkdir(parents=False)
    try:
        quality = run_quality_check(
            candidate,
            out_dir=destination / "quality",
            expect_audio=expect_audio,
            min_score=0,
        )
        duration = float((quality.get("metrics") or {}).get("duration") or 0.0)
        if duration <= 0:
            raise ReviewPackError("review source has no readable duration")
        frames_dir = destination / "frames"
        frames_dir.mkdir()
        try:
            extracted = _extract_frames(candidate, frames_dir, duration)
        except ShotReviewError as exc:
            raise ReviewPackError(str(exc)) from exc
    except QualityCheckError as exc:
        raise ReviewPackError(str(exc)) from exc

    frames = {
        label: _hash_artifact(Path(record["path"])) | {"timestamp_sec": record["timestamp_sec"]}
        for label, record in extracted["frames"].items()
    }
    contact = Path(extracted["contact_sheet"]["path"])
    report = {
        "schema_version": 1,
        "kind": "review-pack",
        "ok": bool(quality.get("decode_ok")) and contact.is_file(),
        "approved": False,
        "human_review_required": True,
        "source": _hash_artifact(candidate),
        "technical_qa": quality,
        "artifacts": {"frames": frames, "contact_sheet": _hash_artifact(contact)},
        "safety": {
            "provider_submission": False,
            "provider_switch": False,
            "manifest_mutation": False,
            "registration": False,
        },
    }
    if download is not None:
        report["download"] = dict(download)
    receipt = destination / "review-pack.json"
    write_json(receipt, report)
    report["path"] = str(receipt)
    return report
