"""Non-commercial MMAudio SFX canaries for the private RTX 5090 node."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import tempfile
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from audio_node_client import AudioNodeError, _validate_wav, render_sfx
from media_duration import MediaDurationError, probe_duration_sec
from performance_candidates import receipt_is_signed, sign_receipt
from util import read_json, write_json


class SFXCandidateError(RuntimeError):
    pass


_SAFE_ID = re.compile(r"^mmaudio-sfx-[a-z0-9_-]{1,64}$")
_APPROVED_STATUS = "approved_noncommercial"
_INTERNAL_SCOPE = "noncommercial_internal"
_ASR_SCREEN_STATUS = "completed_candidate_signal"


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


def _find_pending(root: Path, asset_id: str) -> tuple[Path, dict[str, Any]]:
    if not _SAFE_ID.fullmatch(asset_id):
        raise SFXCandidateError("invalid SFX candidate id")
    receipt = root / "audio" / "candidates" / "sfx" / "pending" / f"{asset_id}.json"
    record = read_json(receipt)
    if not isinstance(record, dict) or record.get("asset_id") != asset_id:
        raise SFXCandidateError("SFX candidate receipt not found")
    return receipt, record


def _approved_receipt(root: Path, asset_id: str) -> tuple[Path, dict[str, Any]]:
    if not _SAFE_ID.fullmatch(asset_id):
        raise SFXCandidateError("invalid SFX candidate id")
    receipt = (
        root
        / "audio"
        / "candidates"
        / "sfx"
        / "approved-noncommercial"
        / f"{asset_id}.receipt.json"
    )
    record = read_json(receipt)
    if (
        not isinstance(record, dict)
        or record.get("asset_id") != asset_id
        or record.get("status") != _APPROVED_STATUS
        or not receipt_is_signed(record)
    ):
        raise SFXCandidateError("approved non-commercial SFX receipt not found")
    return receipt, record


def _speech_like_segments(report: dict[str, Any]) -> int:
    transcript = report.get("transcript")
    entries = transcript.get("segments") if isinstance(transcript, dict) else None
    if not isinstance(entries, list):
        raise SFXCandidateError("ASR speech screen transcript is invalid")
    non_speech_labels = {
        "[silence]",
        "silence",
        "[静音]",
        "静音",
        "[environmental sounds]",
        "environmental sounds",
    }
    return sum(
        1
        for entry in entries
        if isinstance(entry, dict)
        and str(entry.get("text") or "").strip().casefold() not in non_speech_labels
        and str(entry.get("text") or "").strip()
    )


def _speech_screen_valid(root: Path, record: dict[str, Any]) -> bool:
    screen = record.get("asr_speech_screen")
    if not isinstance(screen, dict) or screen.get("status") != _ASR_SCREEN_STATUS:
        return False
    receipt_raw = str(screen.get("receipt") or "")
    if not receipt_raw.startswith("local:"):
        return False
    receipt = root / receipt_raw.removeprefix("local:")
    if not _confined_without_symlinks(root, receipt) or not receipt.is_file():
        return False
    report = read_json(receipt)
    provider = report.get("provider") if isinstance(report, dict) else None
    audio = report.get("inputs", {}).get("audio") if isinstance(report, dict) else None
    if not isinstance(provider, dict) or not isinstance(audio, dict):
        return False
    try:
        speech_like_segments = _speech_like_segments(report)
    except SFXCandidateError:
        return False
    return bool(
        report.get("kind") == "vibevoice-asr-review"
        and report.get("status") == "candidate_only"
        and report.get("human_review_required") is True
        and audio.get("sha256") == record.get("sha256") == screen.get("audio_sha256")
        and provider.get("transcript_sha256") == screen.get("transcript_sha256")
        and _sha256(receipt) == screen.get("report_sha256")
        and len(report.get("transcript", {}).get("segments") or []) == screen.get("segment_count")
        and speech_like_segments == screen.get("speech_like_segment_count")
    )


def screen_speech(root: Path, asset_id: str) -> dict[str, Any]:
    """Bind an ASR leakage signal to a pending MMAudio candidate, never decide approval."""
    from vibevoice_asr_review import VibeVoiceASRError, create_report

    root = root.expanduser().resolve()
    receipt, record = _find_pending(root, asset_id)
    source = root / str(record.get("path") or "")
    if (
        record.get("status") != "pending_human_review"
        or not receipt_is_signed(record)
        or not _confined_without_symlinks(root, source)
        or not source.is_file()
        or _sha256(source) != record.get("sha256")
    ):
        raise SFXCandidateError("SFX candidate is not a valid pending take for ASR screening")
    report_name = Path("sfx-speech-screen") / f"{asset_id}.vibevoice-asr-review.json"
    try:
        report = create_report(root, audio=source, report_name=report_name)
    except VibeVoiceASRError as exc:
        raise SFXCandidateError(f"VibeVoice-ASR speech screen failed: {exc}") from exc
    output = Path(str(report.get("path") or ""))
    try:
        relative = output.resolve().relative_to(root)
    except (OSError, ValueError) as exc:
        raise SFXCandidateError("ASR speech screen receipt escaped film root") from exc
    if not _confined_without_symlinks(root, output) or not output.is_file():
        raise SFXCandidateError("ASR speech screen receipt is invalid")
    provider = report.get("provider")
    audio = (
        report.get("inputs", {}).get("audio") if isinstance(report.get("inputs"), dict) else None
    )
    if (
        not isinstance(provider, dict)
        or not isinstance(audio, dict)
        or report.get("kind") != "vibevoice-asr-review"
        or report.get("status") != "candidate_only"
        or audio.get("sha256") != record.get("sha256")
    ):
        raise SFXCandidateError("ASR speech screen is not bound to the MMAudio candidate")
    speech_like_segments = _speech_like_segments(report)
    record["asr_speech_screen"] = {
        "status": _ASR_SCREEN_STATUS,
        "receipt": f"local:{relative}",
        "audio_sha256": record["sha256"],
        "report_sha256": _sha256(output),
        "transcript_sha256": provider.get("transcript_sha256"),
        "segment_count": len(report.get("transcript", {}).get("segments") or []),
        "speech_like_segment_count": speech_like_segments,
        "speech_like_flagged": speech_like_segments > 0,
        "screened_at": datetime.now(UTC).isoformat(),
        "decision": "human_listening_required",
    }
    sign_receipt(record)
    write_json(receipt, record)
    return {**record, "receipt": str(receipt)}


def approved_event_receipt_valid(root: Path, event: dict[str, Any]) -> bool:
    """Verify that a timeline cue is bound to signed, fully reviewed local bytes."""
    root = root.expanduser().resolve()
    source_raw = str(event.get("source") or event.get("asset") or "")
    receipt_raw = str(event.get("approval_receipt") or "")
    if not source_raw.startswith("local:") or not receipt_raw.startswith("local:"):
        return False
    source = root / source_raw.removeprefix("local:")
    receipt = root / receipt_raw.removeprefix("local:")
    if (
        not _confined_without_symlinks(root, source)
        or not _confined_without_symlinks(root, receipt)
        or not source.is_file()
        or not receipt.is_file()
    ):
        return False
    record = read_json(receipt)
    if not isinstance(record, dict):
        return False
    review = record.get("human_review")
    try:
        source_rel = str(source.relative_to(root))
        actual = _sha256(source)
    except (OSError, ValueError):
        return False
    return bool(
        record.get("schema") == "aifilm-sfx-candidate-v1"
        and record.get("status") == _APPROVED_STATUS
        and record.get("production_eligible") is False
        and record.get("delivery_eligible_scopes") == [_INTERNAL_SCOPE]
        and record.get("approved_path") == source_rel
        and record.get("sha256") == actual == event.get("source_sha256")
        and record.get("license") == event.get("license") == "CC-BY-NC-4.0"
        and record.get("model") == event.get("model") == "hkchengrex/MMAudio-large-44k-v2"
        and re.fullmatch(r"[0-9a-f]{64}", str(record.get("checkpoint_fingerprint") or ""))
        and record.get("checkpoint_fingerprint") == event.get("checkpoint_fingerprint")
        and record.get("node_job_id") == event.get("node_job_id")
        and receipt_is_signed(record)
        and _speech_screen_valid(root, record)
        and isinstance(review, dict)
        and review.get("reviewer")
        and all(
            review.get(field) is True
            for field in (
                "heard_full",
                "sync_confirmed",
                "no_speech_confirmed",
                "no_music_confirmed",
                "artifact_free_confirmed",
                "asr_speech_reviewed",
            )
        )
    )


def approve(
    root: Path,
    asset_id: str,
    *,
    reviewer: str,
    heard_full: bool,
    sync_confirmed: bool,
    no_speech_confirmed: bool,
    no_music_confirmed: bool,
    artifact_free_confirmed: bool,
    asr_speech_reviewed: bool,
) -> dict[str, Any]:
    """Approve a fully heard MMAudio take for internal non-commercial films only."""
    root = root.expanduser().resolve()
    pending_receipt, record = _find_pending(root, asset_id)
    checks = (
        heard_full,
        sync_confirmed,
        no_speech_confirmed,
        no_music_confirmed,
        artifact_free_confirmed,
        asr_speech_reviewed,
    )
    if not reviewer.strip() or not all(value is True for value in checks):
        raise SFXCandidateError(
            "reviewer, ASR acknowledgement, and all listening checks are required"
        )
    if (
        record.get("schema") != "aifilm-sfx-candidate-v1"
        or record.get("status") != "pending_human_review"
        or record.get("production_eligible") is not False
        or record.get("usage_scope") != "noncommercial_internal_research"
        or record.get("license") != "CC-BY-NC-4.0"
        or record.get("model") != "hkchengrex/MMAudio-large-44k-v2"
        or not receipt_is_signed(record)
    ):
        raise SFXCandidateError("SFX candidate is not a valid pending non-commercial take")
    if not _speech_screen_valid(root, record):
        raise SFXCandidateError("valid ASR speech screen is required before approval")
    expected = Path("audio") / "candidates" / "sfx" / "pending" / f"{asset_id}.wav"
    if str(record.get("path") or "") != str(expected):
        raise SFXCandidateError("SFX candidate path does not match its receipt")
    source = root / expected
    if (
        not _confined_without_symlinks(root, source)
        or not source.is_file()
        or _sha256(source) != record.get("sha256")
    ):
        raise SFXCandidateError("SFX candidate is missing or changed")
    _validate_wav(source)
    destination = (
        root / "audio" / "candidates" / "sfx" / "approved-noncommercial" / f"{asset_id}.wav"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not _confined_without_symlinks(root, destination.parent):
        raise SFXCandidateError("SFX approval directory is invalid")
    temporary = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.partial"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    target_fd: int | None = None
    try:
        if destination.exists() or destination.is_symlink():
            raise SFXCandidateError("approved SFX output already exists")
        target_fd = os.open(temporary, flags, 0o600)
        with source.open("rb") as source_handle, os.fdopen(target_fd, "wb") as target_handle:
            target_fd = None
            shutil.copyfileobj(source_handle, target_handle)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        _validate_wav(temporary)
        if _sha256(temporary) != record["sha256"]:
            raise SFXCandidateError("SFX candidate changed while being approved")
        os.replace(temporary, destination)
    finally:
        if target_fd is not None:
            os.close(target_fd)
        temporary.unlink(missing_ok=True)
    record.update(
        {
            "status": _APPROVED_STATUS,
            "production_eligible": False,
            "delivery_eligible_scopes": [_INTERNAL_SCOPE],
            "approved_path": str(destination.relative_to(root)),
            "approved_at": datetime.now(UTC).isoformat(),
            "human_review": {
                "reviewer": reviewer.strip(),
                "heard_full": True,
                "sync_confirmed": True,
                "no_speech_confirmed": True,
                "no_music_confirmed": True,
                "artifact_free_confirmed": True,
                "asr_speech_reviewed": True,
            },
        }
    )
    sign_receipt(record)
    write_json(pending_receipt, record)
    approval_receipt = destination.with_suffix(".receipt.json")
    write_json(approval_receipt, record)
    return {
        **record,
        "receipt": str(pending_receipt),
        "approval_receipt": str(approval_receipt),
    }


def reject(root: Path, asset_id: str, *, reviewer: str, reason: str) -> dict[str, Any]:
    root = root.expanduser().resolve()
    receipt, record = _find_pending(root, asset_id)
    reviewer, reason = reviewer.strip(), reason.strip()
    if (
        record.get("status") != "pending_human_review"
        or not receipt_is_signed(record)
        or not reviewer
        or not reason
        or len(reason) > 240
    ):
        raise SFXCandidateError("pending candidate, reviewer, and concise reason are required")
    record.update(
        {
            "status": "rejected_human_review",
            "rejected_at": datetime.now(UTC).isoformat(),
            "rejected_by": reviewer,
            "rejection_reason": reason,
        }
    )
    sign_receipt(record)
    write_json(receipt, record)
    return {**record, "receipt": str(receipt)}


def _shots(spec: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(spec.get("shots"), list):
        return [shot for shot in spec["shots"] if isinstance(shot, dict)]
    return [
        shot
        for scene in spec.get("scenes") or []
        if isinstance(scene, dict)
        for shot in scene.get("shots") or []
        if isinstance(shot, dict)
    ]


def attach_to_shot(
    root: Path,
    asset_id: str,
    *,
    shot_id: str,
    kind: str,
    start_offset_sec: float,
    duration_sec: float,
    material: str,
    noncommercial_internal_ok: bool,
) -> dict[str, Any]:
    """Attach an approved NC take while making the film's scope explicit."""
    root = root.expanduser().resolve()
    if noncommercial_internal_ok is not True:
        raise SFXCandidateError(
            "explicit non-commercial internal scope acknowledgement is required"
        )
    if kind not in {"foley", "sfx"}:
        raise SFXCandidateError("SFX attachment kind must be foley or sfx")
    if (
        isinstance(start_offset_sec, bool)
        or isinstance(duration_sec, bool)
        or float(start_offset_sec) < 0
        or float(duration_sec) <= 0
    ):
        raise SFXCandidateError("SFX attachment timing is invalid")
    material = material.strip().lower()
    if not material:
        raise SFXCandidateError("SFX material is required")
    approval_receipt, record = _approved_receipt(root, asset_id)
    spec_path = root / "film-spec.json"
    spec = read_json(spec_path)
    if not isinstance(spec, dict):
        raise SFXCandidateError("film-spec.json is required")
    current_scope = str(spec.get("delivery_scope") or "")
    if current_scope not in {"", _INTERNAL_SCOPE}:
        raise SFXCandidateError("MMAudio cannot attach to a commercial film")
    shot = next(
        (row for row in _shots(spec) if str(row.get("id") or row.get("shot_id") or "") == shot_id),
        None,
    )
    if shot is None:
        raise SFXCandidateError("target shot was not found")
    shot_duration = float(shot.get("duration_sec") or 0)
    if float(start_offset_sec) + float(duration_sec) > shot_duration + 1e-6:
        raise SFXCandidateError("SFX attachment exceeds shot duration")
    cue = {
        "kind": kind,
        "start_offset_sec": round(float(start_offset_sec), 3),
        "duration_sec": round(float(duration_sec), 3),
        "asset_hint": "mmaudio_video_synchronized",
        "source": f"local:{record['approved_path']}",
        "license": record["license"],
        "source_sha256": record["sha256"],
        "approval_status": _APPROVED_STATUS,
        "approval_receipt": f"local:{approval_receipt.relative_to(root)}",
        "production_eligible": False,
        "usage_scope": _INTERNAL_SCOPE,
        "model": record["model"],
        "checkpoint_fingerprint": record["checkpoint_fingerprint"],
        "node_job_id": record["node_job_id"],
        "material": material,
        "gain": 1.0,
        "pan": 0.0,
        "fade_in_sec": 0.02,
        "fade_out_sec": 0.05,
    }
    cues = shot.setdefault("audio_cues", [])
    if not isinstance(cues, list):
        raise SFXCandidateError("target shot audio_cues must be an array")
    cues.append(cue)
    from audio_attachment import bind

    cue["attachment_receipt"] = bind(
        root, candidate_kind="sfx", asset_id=asset_id, shot_id=shot_id, cue=cue
    )
    spec["delivery_scope"] = _INTERNAL_SCOPE
    write_json(spec_path, spec)
    return {"ok": True, "asset_id": asset_id, "shot_id": shot_id, "cue": cue}


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
