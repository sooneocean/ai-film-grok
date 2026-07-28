"""Approval-gated local performance candidates for private audio generation."""

from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from audio_node_client import AudioNodeError, _validate_wav, render
from security_policy import atomic_write_text
from util import read_json, write_json

_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
_AUTHORIZATIONS = frozenset({"original", "authorized_reference"})


class PerformanceCandidateError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _pending_dir(root: Path) -> Path:
    return root / "audio" / "candidates" / "performance" / "pending"


def _confined_without_symlinks(root: Path, path: Path) -> bool:
    root = root.resolve()
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return False
    try:
        return path.resolve().is_relative_to(root)
    except OSError:
        return False


def _find(root: Path, asset_id: str) -> tuple[Path, dict[str, Any]]:
    if not _SAFE_ID.fullmatch(asset_id):
        raise PerformanceCandidateError("invalid performance candidate id")
    receipt = _pending_dir(root) / f"{asset_id}.json"
    data = read_json(receipt)
    if not isinstance(data, dict) or data.get("asset_id") != asset_id:
        raise PerformanceCandidateError("performance candidate receipt not found")
    return receipt, data


def _require_valid_wav(path: Path, *, context: str) -> None:
    """Keep local validation failures inside the public candidate error contract."""
    try:
        _validate_wav(path)
    except (AudioNodeError, OSError) as exc:
        raise PerformanceCandidateError(f"{context} is not a valid delivery WAV") from exc


def generate(
    root: Path,
    *,
    base_url: str,
    token: str,
    cue: str,
    duration: float,
    seed: int,
    character_id: str,
    source_authorization: str,
    adult_confirmed: bool,
    model_version: str = "higgs-audio-v2",
) -> dict[str, Any]:
    """Generate only a pending, non-promoted performance take."""
    root = root.expanduser().resolve()
    text = cue.strip()
    if not text or len(text) > 512:
        raise PerformanceCandidateError("performance cue must contain 1-512 characters")
    if not 1 <= duration <= 60:
        raise PerformanceCandidateError("performance duration must be between 1 and 60 seconds")
    if adult_confirmed is not True:
        raise PerformanceCandidateError("performance candidates require adult_confirmed=true")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise PerformanceCandidateError("performance take seed must be an integer")
    if source_authorization not in _AUTHORIZATIONS:
        raise PerformanceCandidateError("performance source authorization is invalid")
    if not _SAFE_ID.fullmatch(character_id):
        raise PerformanceCandidateError("character_id is invalid")
    if not model_version.strip():
        raise PerformanceCandidateError("model_version is required")
    asset_id = f"performance-{character_id}-{seed}-{uuid.uuid4().hex[:10]}"
    wav = _pending_dir(root) / f"{asset_id}.wav"
    try:
        node = render(
            base_url,
            token,
            "performance",
            {"prompt": text, "duration": duration, "seed": seed},
            wav,
        )
    except AudioNodeError as exc:
        raise PerformanceCandidateError(f"private performance node failed: {exc}") from exc
    try:
        _require_valid_wav(wav, context="private performance node output")
        digest = _sha256(wav)
    except (PerformanceCandidateError, OSError):
        wav.unlink(missing_ok=True)
        raise
    if digest != node.get("sha256"):
        wav.unlink(missing_ok=True)
        raise PerformanceCandidateError("private performance node receipt hash mismatch")
    record = {
        "schema": "aifilm-performance-candidate-v1",
        "asset_id": asset_id,
        "status": "pending_human_review",
        "kind": "performance",
        "character_id": character_id,
        "adult_confirmed": True,
        "source_authorization": source_authorization,
        "model_version": model_version,
        "take_seed": seed,
        "duration_sec": duration,
        "node_job_id": node["job_id"],
        "sha256": digest,
        "performance_cue_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "path": str(wav.relative_to(root)),
        "created_at": datetime.now(UTC).isoformat(),
    }
    receipt = _pending_dir(root) / f"{asset_id}.json"
    write_json(receipt, record)
    return {**record, "receipt": str(receipt)}


def approve(root: Path, asset_id: str) -> dict[str, Any]:
    """Promote a human-heard candidate into the performance timeline asset pool."""
    root = root.expanduser().resolve()
    receipt, record = _find(root, asset_id)
    expected = Path("audio") / "candidates" / "performance" / "pending" / f"{asset_id}.wav"
    if (
        record.get("schema") != "aifilm-performance-candidate-v1"
        or record.get("status") != "pending_human_review"
        or record.get("adult_confirmed") is not True
        or record.get("source_authorization") not in _AUTHORIZATIONS
        or not str(record.get("model_version") or "").strip()
        or str(record.get("path") or "") != str(expected)
        or isinstance(record.get("take_seed"), bool)
        or not isinstance(record.get("take_seed"), int)
    ):
        raise PerformanceCandidateError("performance candidate receipt is invalid")
    source = root / expected
    if (
        not _confined_without_symlinks(root, source)
        or not source.is_file()
        or _sha256(source) != record.get("sha256")
    ):
        raise PerformanceCandidateError("performance candidate is missing or its hash changed")
    _require_valid_wav(source, context="performance candidate")
    destination = root / "audio" / "candidates" / "performance" / "approved" / f"{asset_id}.wav"
    if not _confined_without_symlinks(root, destination.parent.parent):
        raise PerformanceCandidateError("performance approval directory is invalid")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not _confined_without_symlinks(root, destination.parent):
        raise PerformanceCandidateError("performance approval directory is invalid")
    temporary = destination.with_suffix(".partial.wav")
    shutil.copyfile(source, temporary)
    if _sha256(temporary) != record["sha256"]:
        temporary.unlink(missing_ok=True)
        raise PerformanceCandidateError("performance candidate changed while being approved")
    _require_valid_wav(temporary, context="approved performance candidate")
    temporary.replace(destination)
    if _sha256(destination) != record["sha256"]:
        destination.unlink(missing_ok=True)
        raise PerformanceCandidateError("approved performance hash mismatch")
    record.update(
        {
            "status": "approved",
            "approved_at": datetime.now(UTC).isoformat(),
            "approved_path": str(destination.relative_to(root)),
        }
    )
    write_json(receipt, record)
    approved_receipt = destination.with_suffix(".receipt.json")
    write_json(approved_receipt, record)
    atomic_write_text(
        destination.with_suffix(".license.txt"),
        "Private original or authorized adult performance candidate; human approved.\n",
    )
    return {**record, "receipt": str(receipt), "approval_receipt": str(approved_receipt)}
