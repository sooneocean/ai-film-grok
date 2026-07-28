"""Non-commercial MMAudio SFX canaries for the private RTX 5090 node."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from audio_node_client import AudioNodeError, _validate_wav, render_sfx
from media_duration import MediaDurationError, probe_duration_sec
from performance_candidates import sign_receipt
from util import write_json


class SFXCandidateError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _prepare_pending(root: Path) -> Path:
    pending = root / "audio" / "candidates" / "sfx" / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    current = root
    try:
        relative = pending.relative_to(root)
    except ValueError as exc:
        raise SFXCandidateError("SFX pending directory escapes the film root") from exc
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise SFXCandidateError("SFX pending directory must not contain symlinks")
    if pending.resolve() != pending or not pending.is_dir():
        raise SFXCandidateError("SFX pending directory is invalid")
    return pending


def generate(
    root: Path,
    *,
    prompt: str,
    duration: float,
    seed: int,
    source_video: Path | None,
    noncommercial_research_ok: bool,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    text = prompt.strip()
    if not 1 <= len(text) <= 512:
        raise SFXCandidateError("SFX prompt must contain 1-512 characters")
    if not 1 <= duration <= 30:
        raise SFXCandidateError("SFX duration must be between 1 and 30 seconds")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise SFXCandidateError("SFX seed must be an integer")
    if noncommercial_research_ok is not True:
        raise SFXCandidateError(
            "MMAudio weights are CC BY-NC 4.0; pass --noncommercial-research-ok only for an internal non-commercial pilot"
        )
    from config_loader import get_config

    get_config()
    base_url = os.environ.get("AIFILM_AUDIO_NODE_URL", "").strip()
    token = os.environ.get("AIFILM_AUDIO_NODE_TOKEN", "").strip()
    if not base_url or not token:
        raise SFXCandidateError("AIFILM_AUDIO_NODE_URL/TOKEN are required for SFX generation")

    asset_id = f"mmaudio-sfx-{seed}-{uuid.uuid4().hex[:10]}"
    pending = _prepare_pending(root)
    wav = pending / f"{asset_id}.wav"
    receipt = pending / f"{asset_id}.json"
    if wav.exists() or wav.is_symlink() or receipt.exists() or receipt.is_symlink():
        raise SFXCandidateError("SFX candidate output already exists")
    try:
        node = render_sfx(
            base_url,
            token,
            prompt=text,
            duration=duration,
            seed=seed,
            out=wav,
            source_video=source_video,
            noncommercial_research_ok=True,
        )
        _validate_wav(wav)
        actual_duration = probe_duration_sec(wav, label="MMAudio SFX candidate")
        tolerance = max(0.5, duration * 0.05)
        if abs(actual_duration - duration) > tolerance:
            raise SFXCandidateError(
                f"MMAudio SFX duration mismatch: requested {duration:.3f}s, got {actual_duration:.3f}s"
            )
    except SFXCandidateError:
        wav.unlink(missing_ok=True)
        raise
    except (AudioNodeError, MediaDurationError, OSError) as exc:
        wav.unlink(missing_ok=True)
        raise SFXCandidateError(f"private MMAudio SFX node failed: {exc}") from exc
    digest = _sha256(wav)
    if digest != node.get("sha256"):
        wav.unlink(missing_ok=True)
        raise SFXCandidateError("private MMAudio SFX receipt hash mismatch")
    record = {
        "schema": "aifilm-sfx-candidate-v1",
        "asset_id": asset_id,
        "status": "pending_human_review",
        "production_eligible": False,
        "usage_scope": "noncommercial_internal_research",
        "license": node["license"],
        "model": node["model"],
        "checkpoint_fingerprint": node["checkpoint_fingerprint"],
        "seed": seed,
        "duration_sec": actual_duration,
        "requested_duration_sec": duration,
        "node_job_id": node["job_id"],
        "sha256": digest,
        "prompt_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "source_video_sha256": node.get("source_video_sha256"),
        "path": str(wav.relative_to(root)),
        "created_at": datetime.now(UTC).isoformat(),
    }
    sign_receipt(record)
    write_json(receipt, record)
    return {**record, "receipt": str(receipt)}
