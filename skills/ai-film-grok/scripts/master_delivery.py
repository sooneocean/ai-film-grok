#!/usr/bin/env python3
"""Hash-bound Master delivery validation from real ffprobe/read-back evidence."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from approval_ledger import approval_is_current, read_approval_ledger
from util import sha256_file as _sha256_file

REQUIRED_ASSETS = (
    "film_final.mp4",
    "final.srt",
    "drama-graph.json",
    "style-bible.json",
    "audio-bible.json",
    "post-bible.json",
    "film-spec.json",
    "edit.edl",
    "provenance.json",
    "receipts/approval-ledger.json",
)


def sha256_file(path: Path) -> str:
    return _sha256_file(path)


def parse_ffprobe(value: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("ffprobe evidence must be an object")
    return parsed


def _run_ffprobe(path: Path) -> dict[str, Any]:
    process = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if process.returncode != 0:
        raise ValueError("ffprobe could not read the current final MP4")
    return parse_ffprobe(process.stdout)


def _full_decode(path: Path) -> None:
    process = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
        check=False,
        capture_output=True,
        text=True,
        timeout=900,
    )
    if process.returncode != 0:
        raise ValueError("full final MP4 decode failed")


def _issue(code: str, message: str, *, ref: str | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "ref": ref}


def _evidence_file_current(
    base: Path, item: dict[str, Any], *, ref_key: str, hash_key: str
) -> bool:
    relative = item.get(ref_key)
    if not isinstance(relative, str) or not relative:
        return False
    path = (base / relative).resolve()
    return path.is_relative_to(base) and path.is_file() and item.get(hash_key) == sha256_file(path)


def validate_master_delivery(
    root: Path | str,
    *,
    delivery: dict[str, Any],
) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    issues: list[dict[str, Any]] = []
    recorded_assets = delivery.get("assets") if isinstance(delivery.get("assets"), dict) else {}
    actual_hashes: dict[str, str] = {}
    for relative in REQUIRED_ASSETS:
        path = base / relative
        if not path.is_file():
            issues.append(
                _issue("REQUIRED_ASSET_MISSING", "delivery asset is missing", ref=relative)
            )
            continue
        actual = sha256_file(path)
        actual_hashes[relative] = actual
        if recorded_assets.get(relative) != actual:
            issues.append(
                _issue("ASSET_HASH_MISMATCH", "delivery asset hash changed", ref=relative)
            )

    final_path = base / "film_final.mp4"
    try:
        probe = _run_ffprobe(final_path)
        _full_decode(final_path)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        probe = {}
        issues.append(_issue("MASTER_READBACK_FAILED", str(exc), ref="film_final.mp4"))
    streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if video is None:
        issues.append(_issue("VIDEO_STREAM_MISSING", "ffprobe found no video stream"))
    elif int(video.get("height") or 0) <= int(video.get("width") or 0):
        issues.append(_issue("ASPECT_NOT_VERTICAL", "master is not vertical"))
    if audio is None:
        issues.append(_issue("AUDIO_STREAM_MISSING", "ffprobe found no audio stream"))
    try:
        duration = float((probe.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        issues.append(_issue("DURATION_INVALID", "ffprobe duration is not positive"))

    final_hash = actual_hashes.get("film_final.mp4")
    srt_hash = actual_hashes.get("final.srt")
    motion = [item for item in delivery.get("motion_evidence") or [] if isinstance(item, dict)]
    motion_current = any(
        item.get("kind") == "decoded-frame-delta"
        and float(item.get("score") or 0) > 0
        and item.get("final_sha256") == final_hash
        and _evidence_file_current(base, item, ref_key="evidence_ref", hash_key="evidence_sha256")
        for item in motion
    )
    if not motion_current:
        issues.append(
            _issue("MOTION_EVIDENCE_STALE", "decoded motion evidence is missing or stale")
        )

    caption = (
        delivery.get("caption_attestation")
        if isinstance(delivery.get("caption_attestation"), dict)
        else {}
    )
    if not (
        caption.get("visible") is True
        and caption.get("final_sha256") == final_hash
        and caption.get("srt_sha256") == srt_hash
        and _evidence_file_current(base, caption, ref_key="frame_ref", hash_key="frame_sha256")
    ):
        issues.append(
            _issue("CAPTION_ATTESTATION_STALE", "visible caption evidence is missing or stale")
        )

    screening = (
        delivery.get("full_screening") if isinstance(delivery.get("full_screening"), dict) else {}
    )
    approval_ref = screening.get("approval_ref")
    approval = next(
        (
            item
            for item in read_approval_ledger(base).get("approvals") or []
            if item.get("approval_id") == approval_ref
        ),
        None,
    )
    approval_inputs = {
        relative: digest
        for relative, digest in actual_hashes.items()
        if relative != "receipts/approval-ledger.json"
    }
    human_screening = bool(
        isinstance(approval, dict)
        and approval.get("revoked") is not True
        and approval.get("project_binding_current") is True
        and approval.get("ledger_integrity_current") is True
        and approval.get("approver_type") in {"human", "user"}
        and approval.get("scope") == "master"
        and approval.get("approval_type") == "master_lock"
        and approval_is_current(approval, approval_inputs).get("ok")
    )
    if not human_screening:
        issues.append(
            _issue("FULL_SCREENING_MISSING", "full-film human screening approval is required")
        )

    try:
        from narrative_evidence import validate_narrative_evidence

        narrative = validate_narrative_evidence(base, require_verified=True)
        if narrative.get("required") and not narrative.get("ok"):
            issues.append(
                _issue(
                    "NARRATIVE_EVIDENCE_UNVERIFIED",
                    "episode hooks and plot points lack current executed/human evidence",
                )
            )
    except Exception as exc:  # noqa: BLE001
        issues.append(_issue("NARRATIVE_EVIDENCE_READ_FAILED", str(exc)[:200]))

    if final_hash and recorded_assets.get("film_final.mp4") != final_hash:
        if not any(item["code"] == "MOTION_EVIDENCE_STALE" for item in issues):
            issues.append(
                _issue("MOTION_EVIDENCE_STALE", "final replacement invalidated motion evidence")
            )
        if not any(item["code"] == "CAPTION_ATTESTATION_STALE" for item in issues):
            issues.append(
                _issue(
                    "CAPTION_ATTESTATION_STALE", "final replacement invalidated caption evidence"
                )
            )
        if not any(item["code"] == "SCREENING_APPROVAL_STALE" for item in issues):
            issues.append(
                _issue(
                    "SCREENING_APPROVAL_STALE", "final replacement invalidated screening approval"
                )
            )

    return {
        "ok": not issues,
        "kind": "master-delivery-gate",
        "duration_sec": duration,
        "final_sha256": final_hash,
        "srt_sha256": srt_hash,
        "human_approval_required": True,
        "automated_result": "advisory",
        "issues": issues,
    }
