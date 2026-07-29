"""Approval-gated Stable Audio ambience candidates."""

from __future__ import annotations

import hashlib
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from audio_node_client import AudioNodeError, _validate_wav, render_ambient
from util import read_json, write_json


class AmbienceCandidateError(RuntimeError):
    pass


def _pending(root: Path) -> Path:
    return root / "audio" / "candidates" / "ambience" / "pending"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(
    root: Path, *, base_url: str, token: str, prompt: str, duration: float, seed: int
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not 1 <= len(prompt.strip()) <= 512 or not 1 <= duration <= 47 or isinstance(seed, bool):
        raise AmbienceCandidateError("invalid Stable Audio ambience request")
    asset_id = f"ambience-{seed}-{uuid.uuid4().hex[:10]}"
    wav = _pending(root) / f"{asset_id}.wav"
    try:
        result = render_ambient(
            base_url, token, prompt=prompt, duration=duration, seed=seed, out=wav
        )
        _validate_wav(wav)
    except (AudioNodeError, OSError) as exc:
        wav.unlink(missing_ok=True)
        raise AmbienceCandidateError(f"private Stable Audio node failed: {exc}") from exc
    digest = _digest(wav)
    if digest != result.get("sha256"):
        wav.unlink(missing_ok=True)
        raise AmbienceCandidateError("Stable Audio receipt hash mismatch")
    record = {
        "schema": "aifilm-ambience-candidate-v1",
        "asset_id": asset_id,
        "status": "pending_human_review",
        "kind": "ambience",
        "model": result["model"],
        "license": result["license"],
        "production_eligible": False,
        "take_seed": seed,
        "duration_sec": duration,
        "node_job_id": result["job_id"],
        "sha256": digest,
        "prompt_sha256": hashlib.sha256(prompt.strip().encode()).hexdigest(),
        "path": str(wav.relative_to(root)),
        "created_at": datetime.now(UTC).isoformat(),
    }
    receipt = wav.with_suffix(".json")
    write_json(receipt, record)
    return {**record, "receipt": str(receipt)}


def list_candidates(root: Path) -> list[dict[str, Any]]:
    root = root.expanduser().resolve()
    rows = []
    for receipt in (root / "audio" / "candidates" / "ambience").glob("*/*.json"):
        data = read_json(receipt)
        if isinstance(data, dict) and data.get("schema") == "aifilm-ambience-candidate-v1":
            rows.append(data)
    return sorted(rows, key=lambda row: str(row.get("created_at") or ""))


def approve(root: Path, asset_id: str, *, reviewer: str) -> dict[str, Any]:
    root = root.expanduser().resolve()
    receipt = _pending(root) / f"{asset_id}.json"
    record = read_json(receipt)
    source = _pending(root) / f"{asset_id}.wav"
    if (
        not isinstance(record, dict)
        or record.get("status") != "pending_human_review"
        or not reviewer.strip()
    ):
        raise AmbienceCandidateError("candidate requires an explicit reviewer")
    pending_root = _pending(root).resolve()
    if source.is_symlink() or not source.resolve().is_relative_to(pending_root):
        raise AmbienceCandidateError("candidate WAV must be a local pending file")
    if not source.is_file() or _digest(source) != record.get("sha256"):
        raise AmbienceCandidateError("candidate WAV is missing or changed")
    _validate_wav(source)
    target = root / "audio" / "candidates" / "ambience" / "approved" / f"{asset_id}.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    _validate_wav(target)
    if _digest(target) != record["sha256"]:
        target.unlink(missing_ok=True)
        raise AmbienceCandidateError("approved ambience hash mismatch")
    record.update(
        {
            "status": "approved",
            "reviewer": reviewer.strip(),
            "approved_at": datetime.now(UTC).isoformat(),
            "approved_path": str(target.relative_to(root)),
        }
    )
    write_json(receipt, record)
    write_json(target.with_suffix(".receipt.json"), record)
    return record
