"""Approval-gated Stable Audio ambience candidates."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from audio_node_client import AudioNodeError, _validate_wav, render_ambient
from performance_candidates import receipt_is_signed, sign_receipt
from util import read_json, write_json


class AmbienceCandidateError(RuntimeError):
    pass


_APPROVED_STATUS = "approved_noncommercial"
_INTERNAL_SCOPE = "noncommercial_internal"


def _pending(root: Path) -> Path:
    return root / "audio" / "candidates" / "ambience" / "pending"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _candidate_paths(root: Path, asset_id: str) -> tuple[Path, Path]:
    if not asset_id.startswith("ambience-") or "/" in asset_id or "\\" in asset_id:
        raise AmbienceCandidateError("invalid ambience candidate id")
    pending = _pending(root)
    return pending / f"{asset_id}.wav", pending / f"{asset_id}.json"


def _approved_receipt(root: Path, asset_id: str) -> tuple[Path, dict[str, Any]]:
    if not asset_id.startswith("ambience-") or "/" in asset_id or "\\" in asset_id:
        raise AmbienceCandidateError("invalid ambience candidate id")
    receipt = (
        root
        / "audio"
        / "candidates"
        / "ambience"
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
        raise AmbienceCandidateError("approved non-commercial ambience receipt not found")
    return receipt, record


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
        "checkpoint_sha256": result["checkpoint_sha256"],
        "adapter_sha256": result["adapter_sha256"],
        "production_eligible": False,
        "take_seed": seed,
        "duration_sec": duration,
        "node_job_id": result["job_id"],
        "sha256": digest,
        "prompt_sha256": hashlib.sha256(prompt.strip().encode()).hexdigest(),
        "path": str(wav.relative_to(root)),
        "created_at": datetime.now(UTC).isoformat(),
    }
    sign_receipt(record)
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


def approve(
    root: Path,
    asset_id: str,
    *,
    reviewer: str,
    heard_full: bool,
    no_speech_confirmed: bool,
    no_music_confirmed: bool,
    artifact_free_confirmed: bool,
) -> dict[str, Any]:
    root = root.expanduser().resolve()
    source, receipt = _candidate_paths(root, asset_id)
    record = read_json(receipt)
    if (
        not isinstance(record, dict)
        or record.get("status") != "pending_human_review"
        or not reviewer.strip()
        or not all((heard_full, no_speech_confirmed, no_music_confirmed, artifact_free_confirmed))
        or not receipt_is_signed(record)
    ):
        raise AmbienceCandidateError("candidate requires a complete explicit listening review")
    pending_root = _pending(root)
    if not _confined_without_symlinks(root, source) or not _confined_without_symlinks(
        root, pending_root
    ):
        raise AmbienceCandidateError("candidate WAV must be a local pending file")
    if not source.is_file() or _digest(source) != record.get("sha256"):
        raise AmbienceCandidateError("candidate WAV is missing or changed")
    _validate_wav(source)
    target = (
        root / "audio" / "candidates" / "ambience" / "approved-noncommercial" / f"{asset_id}.wav"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if (
        not _confined_without_symlinks(root, target.parent)
        or target.exists()
        or target.is_symlink()
    ):
        raise AmbienceCandidateError("approved ambience output already exists")
    temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.partial"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        with (
            source.open("rb") as input_handle,
            os.fdopen(os.open(temporary, flags, 0o600), "wb") as output_handle,
        ):
            shutil.copyfileobj(input_handle, output_handle)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        _validate_wav(temporary)
        if _digest(temporary) != record["sha256"]:
            raise AmbienceCandidateError("approved ambience hash mismatch")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    record.update(
        {
            "status": _APPROVED_STATUS,
            "production_eligible": False,
            "delivery_eligible_scopes": [_INTERNAL_SCOPE],
            "reviewer": reviewer.strip(),
            "approved_at": datetime.now(UTC).isoformat(),
            "approved_path": str(target.relative_to(root)),
            "human_review": {
                "reviewer": reviewer.strip(),
                "heard_full": True,
                "no_speech_confirmed": True,
                "no_music_confirmed": True,
                "artifact_free_confirmed": True,
            },
        }
    )
    sign_receipt(record)
    write_json(receipt, record)
    write_json(target.with_suffix(".receipt.json"), record)
    return record


def approved_event_receipt_valid(root: Path, event: dict[str, Any]) -> bool:
    """Bind an ambience timeline event to signed, fully heard local bytes."""
    root = root.expanduser().resolve()
    source_raw = str(event.get("source") or "")
    receipt_raw = str(event.get("approval_receipt") or "")
    if not source_raw.startswith("local:") or not receipt_raw.startswith("local:"):
        return False
    source = root / source_raw.removeprefix("local:")
    receipt = root / receipt_raw.removeprefix("local:")
    try:
        if not _confined_without_symlinks(root, source) or not _confined_without_symlinks(
            root, receipt
        ):
            return False
        source_rel = str(source.resolve().relative_to(root))
        receipt.resolve().relative_to(root)
        actual = _digest(source)
    except (OSError, ValueError):
        return False
    record = read_json(receipt)
    review = record.get("human_review") if isinstance(record, dict) else None
    return bool(
        source.is_file()
        and isinstance(record, dict)
        and record.get("schema") == "aifilm-ambience-candidate-v1"
        and record.get("status") == _APPROVED_STATUS
        and record.get("production_eligible") is False
        and record.get("delivery_eligible_scopes") == [_INTERNAL_SCOPE]
        and record.get("approved_path") == source_rel
        and record.get("sha256") == actual == event.get("source_sha256")
        and record.get("license") == event.get("license") == "Stability AI Community License"
        and record.get("model") == event.get("model")
        and record.get("node_job_id") == event.get("node_job_id")
        and record.get("checkpoint_sha256") == event.get("checkpoint_sha256")
        and record.get("adapter_sha256") == event.get("adapter_sha256")
        and receipt_is_signed(record)
        and isinstance(review, dict)
        and review.get("reviewer")
        and all(
            review.get(field) is True
            for field in (
                "heard_full",
                "no_speech_confirmed",
                "no_music_confirmed",
                "artifact_free_confirmed",
            )
        )
    )


def attach_to_shot(
    root: Path,
    asset_id: str,
    *,
    shot_id: str,
    start_offset_sec: float,
    duration_sec: float,
    acoustic_space: str,
    noncommercial_internal_ok: bool,
) -> dict[str, Any]:
    """Attach a reviewed ambience bed without silently widening its license scope."""
    from project_state import assert_audio_mutation_safe

    try:
        assert_audio_mutation_safe(root)
    except ValueError as exc:
        raise AmbienceCandidateError(str(exc)) from exc
    if noncommercial_internal_ok is not True:
        raise AmbienceCandidateError(
            "explicit non-commercial internal scope acknowledgement is required"
        )
    root = root.expanduser().resolve()
    if float(start_offset_sec) < 0 or float(duration_sec) <= 0 or not acoustic_space.strip():
        raise AmbienceCandidateError("ambience attachment timing and acoustic space are required")
    approval_receipt, record = _approved_receipt(root, asset_id)
    approved_path = root / str(record.get("approved_path") or "")
    if (
        not _confined_without_symlinks(root, approval_receipt)
        or not _confined_without_symlinks(root, approved_path)
        or not approved_path.is_file()
        or _digest(approved_path) != record.get("sha256")
    ):
        raise AmbienceCandidateError("approved ambience asset is not a confined local file")
    spec_path = root / "film-spec.json"
    spec = read_json(spec_path)
    if not isinstance(spec, dict) or str(spec.get("delivery_scope") or "") not in {
        "",
        _INTERNAL_SCOPE,
    }:
        raise AmbienceCandidateError("Stable Audio ambience cannot attach to a commercial film")
    shots = (
        spec.get("shots")
        if isinstance(spec.get("shots"), list)
        else [
            shot
            for scene in spec.get("scenes") or []
            if isinstance(scene, dict)
            for shot in scene.get("shots") or []
            if isinstance(shot, dict)
        ]
    )
    shot = next(
        (row for row in shots if str(row.get("id") or row.get("shot_id") or "") == shot_id), None
    )
    if (
        not isinstance(shot, dict)
        or float(start_offset_sec) + float(duration_sec)
        > float(shot.get("duration_sec") or 0) + 1e-6
    ):
        raise AmbienceCandidateError(
            "ambience attachment target is invalid or exceeds shot duration"
        )
    cue = {
        "kind": "ambience",
        "start_offset_sec": round(float(start_offset_sec), 3),
        "duration_sec": round(float(duration_sec), 3),
        "asset_hint": acoustic_space.strip(),
        "source": f"local:{record['approved_path']}",
        "license": record["license"],
        "source_sha256": record["sha256"],
        "approval_status": _APPROVED_STATUS,
        "approval_receipt": f"local:{approval_receipt.relative_to(root)}",
        "production_eligible": False,
        "usage_scope": _INTERNAL_SCOPE,
        "model": record["model"],
        "node_job_id": record["node_job_id"],
        "checkpoint_sha256": record["checkpoint_sha256"],
        "adapter_sha256": record["adapter_sha256"],
        "gain": 1.0,
        "pan": 0.0,
        "fade_in_sec": 0.3,
        "fade_out_sec": 0.5,
    }
    cues = shot.setdefault("audio_cues", [])
    if not isinstance(cues, list):
        raise AmbienceCandidateError("target shot audio_cues must be an array")
    cues.append(cue)
    from audio_attachment import bind

    cue["attachment_receipt"] = bind(
        root, candidate_kind="ambience", asset_id=asset_id, shot_id=shot_id, cue=cue
    )
    spec["delivery_scope"] = _INTERNAL_SCOPE
    write_json(spec_path, spec)
    return {"ok": True, "asset_id": asset_id, "shot_id": shot_id, "cue": cue}
