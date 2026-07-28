"""Non-commercial MMAudio SFX canaries for the private RTX 5090 node."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import uuid
from contextlib import suppress
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
    absolute = Path(os.path.abspath(root))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.exists() and current.is_symlink():
            raise SFXCandidateError("film root must not contain symlinks")
    root.mkdir(parents=True, exist_ok=True)
    pending = root / "audio" / "candidates" / "sfx" / "pending"
    current = root
    for part in ("audio", "candidates", "sfx", "pending"):
        current = current / part
        if current.exists() and current.is_symlink():
            raise SFXCandidateError("SFX pending directory must not contain symlinks")
        current.mkdir(exist_ok=True)
        if current.is_symlink():
            raise SFXCandidateError("SFX pending directory must not contain symlinks")
    if pending.resolve() != pending or not pending.is_dir():
        raise SFXCandidateError("SFX pending directory is invalid")
    return pending


def _pending_matches_open_directory(pending: Path, directory_fd: int) -> bool:
    try:
        current = os.stat(pending, follow_symlinks=False)
        opened = os.fstat(directory_fd)
    except OSError:
        return False
    return bool(
        stat.S_ISDIR(current.st_mode)
        and current.st_dev == opened.st_dev
        and current.st_ino == opened.st_ino
    )


def _copy_into_open_directory(
    directory_fd: int,
    source: Path,
    final_name: str,
) -> None:
    partial_name = f".{final_name}.{uuid.uuid4().hex}.partial"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    target_fd: int | None = None
    try:
        target_fd = os.open(partial_name, flags, 0o600, dir_fd=directory_fd)
        with source.open("rb") as source_handle, os.fdopen(target_fd, "wb") as target_handle:
            target_fd = None
            for block in iter(lambda: source_handle.read(1024 * 1024), b""):
                target_handle.write(block)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        os.link(
            partial_name,
            final_name,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
    finally:
        if target_fd is not None:
            os.close(target_fd)
        with suppress(FileNotFoundError):
            os.unlink(partial_name, dir_fd=directory_fd)


def _publish_candidate(
    pending: Path,
    staged_wav: Path,
    staged_receipt: Path,
    *,
    wav_name: str,
    receipt_name: str,
) -> None:
    if not all(
        operation in os.supports_dir_fd for operation in (os.open, os.stat, os.unlink, os.link)
    ):
        raise SFXCandidateError("secure SFX candidate promotion is unavailable")
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        directory_fd = os.open(pending, flags)
    except OSError as exc:
        raise SFXCandidateError("SFX pending directory is invalid") from exc
    published: list[str] = []
    try:
        if not _pending_matches_open_directory(pending, directory_fd):
            raise SFXCandidateError("SFX pending directory changed during promotion")
        for name in (wav_name, receipt_name):
            try:
                os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise SFXCandidateError("SFX candidate output already exists")
        _copy_into_open_directory(directory_fd, staged_wav, wav_name)
        published.append(wav_name)
        _copy_into_open_directory(directory_fd, staged_receipt, receipt_name)
        published.append(receipt_name)
        if not _pending_matches_open_directory(pending, directory_fd):
            raise SFXCandidateError("SFX pending directory changed during promotion")
    except Exception as exc:
        for name in reversed(published):
            with suppress(FileNotFoundError):
                os.unlink(name, dir_fd=directory_fd)
        if isinstance(exc, SFXCandidateError):
            raise
        raise SFXCandidateError("secure SFX candidate promotion failed") from exc
    finally:
        os.close(directory_fd)


def generate(
    root: Path,
    *,
    prompt: str,
    duration: float,
    seed: int,
    source_video: Path | None,
    noncommercial_research_ok: bool,
) -> dict[str, Any]:
    root_input = root.expanduser()
    if root_input.is_symlink():
        raise SFXCandidateError("film root must not be symlinked")
    root = Path(os.path.abspath(root_input))
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
    _prepare_pending(root)
    with tempfile.TemporaryDirectory(prefix="aifilm-mmaudio-sfx-") as temporary:
        staged_wav = Path(temporary) / f"{asset_id}.wav"
        try:
            node = render_sfx(
                base_url,
                token,
                prompt=text,
                duration=duration,
                seed=seed,
                out=staged_wav,
                source_video=source_video,
                noncommercial_research_ok=True,
            )
            _validate_wav(staged_wav)
            actual_duration = probe_duration_sec(staged_wav, label="MMAudio SFX candidate")
            tolerance = max(0.5, duration * 0.05)
            if abs(actual_duration - duration) > tolerance:
                raise SFXCandidateError(
                    f"MMAudio SFX duration mismatch: requested {duration:.3f}s, got {actual_duration:.3f}s"
                )
        except SFXCandidateError:
            raise
        except (AudioNodeError, MediaDurationError, OSError) as exc:
            raise SFXCandidateError(f"private MMAudio SFX node failed: {exc}") from exc
        digest = _sha256(staged_wav)
        if digest != node.get("sha256"):
            raise SFXCandidateError("private MMAudio SFX receipt hash mismatch")
        pending = _prepare_pending(root)
        wav = pending / f"{asset_id}.wav"
        receipt = pending / f"{asset_id}.json"
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
        staged_receipt = Path(temporary) / f"{asset_id}.json"
        write_json(staged_receipt, record)
        _publish_candidate(
            pending,
            staged_wav,
            staged_receipt,
            wav_name=wav.name,
            receipt_name=receipt.name,
        )
    return {**record, "receipt": str(receipt)}
