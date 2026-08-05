"""Auditable, approval-gated ACE-Step BGM candidates for a film workspace."""

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
_SAFE_MOOD = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class BGMCandidateError(RuntimeError):
    pass


from util import sha256_file


def _pending_dir(root: Path) -> Path:
    return root / "audio" / "candidates" / "bgm" / "pending"


def _confined_without_symlinks(root: Path, path: Path) -> bool:
    """Require an existing path to remain inside root without symlink hops."""
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
        raise BGMCandidateError("invalid BGM candidate id")
    receipt = _pending_dir(root) / f"{asset_id}.json"
    data = read_json(receipt)
    if not isinstance(data, dict) or data.get("asset_id") != asset_id:
        raise BGMCandidateError("BGM candidate receipt not found")
    return receipt, data


def generate(
    root: Path,
    *,
    base_url: str,
    token: str,
    prompt: str,
    mood: str,
    duration: float,
    seed: int,
) -> dict[str, Any]:
    """Generate a pending candidate; it cannot enter a final automatically."""
    root = root.expanduser().resolve()
    text = prompt.strip()
    if not text or len(text) > 512:
        raise BGMCandidateError("BGM prompt must contain 1-512 characters")
    if not 10 <= duration <= 600:
        raise BGMCandidateError("ACE-Step BGM duration must be between 10 and 600 seconds")
    mood_slug = re.sub(r"[^a-z0-9_-]+", "-", mood.lower()).strip("-") or "rnb"
    asset_id = f"{mood_slug}-{seed}-{uuid.uuid4().hex[:10]}"
    pending = _pending_dir(root)
    wav = pending / f"{asset_id}.wav"
    try:
        node = render(
            base_url,
            token,
            "music",
            {"prompt": text, "duration": duration, "seed": seed},
            wav,
        )
    except AudioNodeError as exc:
        raise BGMCandidateError(f"private ACE-Step node failed: {exc}") from exc
    _validate_wav(wav)
    file_hash = sha256_file(wav)
    if file_hash != node.get("sha256"):
        wav.unlink(missing_ok=True)
        raise BGMCandidateError("private ACE-Step node receipt hash mismatch")
    record = {
        "schema": "aifilm-bgm-candidate-v1",
        "asset_id": asset_id,
        "status": "pending_human_review",
        "kind": "bgm",
        "mood": mood_slug,
        "duration_sec": duration,
        "seed": seed,
        "model": "ACE-Step-1.5",
        "source": "private_audio_node",
        "node_job_id": node["job_id"],
        "sha256": file_hash,
        "prompt_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "path": str(wav.relative_to(root)),
        "created_at": datetime.now(UTC).isoformat(),
    }
    receipt = pending / f"{asset_id}.json"
    write_json(receipt, record)
    return {**record, "receipt": str(receipt)}


def approve(root: Path, asset_id: str) -> dict[str, Any]:
    """Promote a heard-and-approved candidate into the final's local template pool."""
    root = root.expanduser().resolve()
    receipt, record = _find(root, asset_id)
    if (
        record.get("schema") != "aifilm-bgm-candidate-v1"
        or record.get("status") != "pending_human_review"
    ):
        raise BGMCandidateError("only pending BGM candidates can be approved")
    mood = str(record.get("mood") or "")
    if not _SAFE_MOOD.fullmatch(mood):
        raise BGMCandidateError("BGM candidate mood is invalid")
    expected_rel = Path("audio") / "candidates" / "bgm" / "pending" / f"{asset_id}.wav"
    if str(record.get("path") or "") != str(expected_rel):
        raise BGMCandidateError("BGM candidate path is invalid")
    source = root / expected_rel
    if (
        not _confined_without_symlinks(root, source)
        or not source.is_file()
        or sha256_file(source) != record.get("sha256")
    ):
        raise BGMCandidateError("BGM candidate is missing or its hash changed")
    _validate_wav(source)
    destination = root / "audio" / "templates" / mood / f"{asset_id}.wav"
    template_root = root / "audio" / "templates"
    if not _confined_without_symlinks(root, template_root.parent):
        raise BGMCandidateError("BGM template directory is invalid")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not _confined_without_symlinks(root, destination.parent):
        raise BGMCandidateError("BGM template directory is invalid")
    temporary = destination.with_suffix(".partial.wav")
    shutil.copyfile(source, temporary)
    if sha256_file(temporary) != record["sha256"]:
        temporary.unlink(missing_ok=True)
        raise BGMCandidateError("BGM candidate changed while being approved")
    _validate_wav(temporary)
    temporary.replace(destination)
    if sha256_file(destination) != record["sha256"]:
        destination.unlink(missing_ok=True)
        raise BGMCandidateError("approved BGM hash mismatch")
    record.update(
        {
            "status": "approved",
            "approved_at": datetime.now(UTC).isoformat(),
            "approved_path": str(destination.relative_to(root)),
        }
    )
    write_json(receipt, record)
    write_json(destination.with_suffix(".receipt.json"), record)
    atomic_write_text(
        destination.with_suffix(".license.txt"),
        "ACE-Step-1.5 local generative candidate; human approved. Verify model license before release.\n",
    )
    return {**record, "receipt": str(receipt)}


def list_candidates(root: Path) -> list[dict[str, Any]]:
    root = root.expanduser().resolve()
    result: list[dict[str, Any]] = []
    for receipt in sorted(_pending_dir(root).glob("*.json")):
        data = read_json(receipt)
        if isinstance(data, dict) and data.get("schema") == "aifilm-bgm-candidate-v1":
            result.append({**data, "receipt": str(receipt)})
    return result
