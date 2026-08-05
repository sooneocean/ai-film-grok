"""Render checksum-bound local scene-sound assets into an independent stem."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import numpy as np
from audio_timeline import (
    is_approved_internal_ambience,
    is_approved_internal_sfx,
    is_candidate_only_license,
    is_noncommercial_license,
)


class SceneSoundError(ValueError):
    pass


def _nonproduction_sfx_hashes(root: Path) -> set[str]:
    """Deny known pending/NC candidate bytes even after copy or rename."""
    pending = root / "audio" / "candidates" / "sfx" / "pending"
    if not pending.is_dir() or pending.is_symlink():
        return set()
    blocked: set[str] = set()
    for candidate in pending.glob("*.wav"):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        try:
            blocked.add(hashlib.sha256(candidate.read_bytes()).hexdigest())
        except OSError:
            continue
    for receipt in pending.glob("*.json"):
        if receipt.is_symlink():
            continue
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or data.get("schema") != "aifilm-sfx-candidate-v1":
            continue
        digest = str(data.get("sha256") or "")
        if len(digest) == 64 and all(
            character in "0123456789abcdef" for character in digest.lower()
        ):
            blocked.add(digest.lower())
    return blocked


def _approved_performance(root: Path, event: dict[str, Any], asset: Path, actual: str) -> None:
    """Bind a performance timeline entry to its human-approved local receipt."""
    raw = str(event.get("approval_receipt") or "")
    if not raw.startswith("local:"):
        raise SceneSoundError(f"{event.get('id')}: approved performance receipt is required")
    try:
        receipt_path = (root / raw.removeprefix("local:")).resolve()
        receipt_path.relative_to(root)
        data = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SceneSoundError(
            f"{event.get('id')}: approved performance receipt is unreadable"
        ) from exc
    if not isinstance(data, dict):
        raise SceneSoundError(f"{event.get('id')}: approved performance receipt is invalid")
    try:
        source_rel = str(asset.relative_to(root))
    except ValueError as exc:
        raise SceneSoundError(f"{event.get('id')}: performance asset escapes film root") from exc
    try:
        from performance_candidates import receipt_is_signed

        signed = receipt_is_signed(data)
    except Exception:
        signed = False
    if (
        data.get("schema") != "aifilm-performance-candidate-v1"
        or data.get("status") != "approved"
        or not signed
        or data.get("approved_path") != source_rel
        or data.get("sha256") != actual
        or data.get("adult_confirmed") is not True
        or event.get("adult_confirmed") is not True
        or data.get("source_authorization") not in {"original", "authorized_reference"}
        or data.get("source_authorization") != event.get("source_authorization")
        or data.get("character_id") != event.get("character_id")
        or data.get("language") != "nonverbal"
        or event.get("language") != "nonverbal"
        or data.get("language") != event.get("language")
        or data.get("node_job_id") != event.get("node_job_id")
        or data.get("take_seed") != event.get("take_seed")
        or data.get("model_version") != event.get("model_version")
    ):
        raise SceneSoundError(
            f"{event.get('id')}: performance approval receipt does not bind asset"
        )


def _approved_internal_sfx(
    root: Path,
    event: dict[str, Any],
    asset: Path,
    actual: str,
    delivery_scope: str,
) -> bool:
    """Bind an NC-only scene cue to its signed, fully heard approval receipt."""
    if not is_approved_internal_sfx(event, delivery_scope):
        return False
    source = str(event.get("source") or "")
    try:
        from sfx_candidates import approved_event_receipt_valid

        if source.startswith("library:"):
            return bool(
                approved_event_receipt_valid(root, event) and actual == event.get("source_sha256")
            )
        source_rel = str(asset.relative_to(root))
    except ValueError:
        return False
    return bool(
        approved_event_receipt_valid(root, event)
        and source_rel == str(event.get("source") or "").removeprefix("local:")
        and actual == event.get("source_sha256")
    )


def _approved_internal_ambience(
    root: Path, event: dict[str, Any], asset: Path, actual: str, delivery_scope: str
) -> bool:
    if not is_approved_internal_ambience(event, delivery_scope):
        return False
    try:
        from ambience_candidates import approved_event_receipt_valid

        return (
            approved_event_receipt_valid(root, event)
            and str(asset.relative_to(root))
            == str(event.get("source") or "").removeprefix("local:")
            and actual == event.get("source_sha256")
        )
    except (OSError, ValueError):
        return False


def _apply_event_controls(
    samples: np.ndarray, event: dict[str, Any], sample_rate: int
) -> np.ndarray:
    """Apply the signed event gain, pan and fades before it enters the bed."""
    out = samples.astype(np.float32, copy=True)
    out *= float(event.get("gain", 1.0))
    pan = float(event.get("pan", 0.0))
    left, right = (1.0 - pan) / 2.0, (1.0 + pan) / 2.0
    out[:, 0] *= left
    out[:, 1] *= right
    for key, edge in (("fade_in_sec", "in"), ("fade_out_sec", "out")):
        count = min(len(out), int(round(float(event.get(key, 0.0)) * sample_rate)))
        if count <= 0:
            continue
        ramp = np.linspace(0.0, 1.0, count, dtype=np.float32)
        if edge == "in":
            out[:count] *= ramp[:, None]
        else:
            out[-count:] *= ramp[::-1, None]
    return out


def _open_confined_asset(root: Path, relative: Path) -> int:
    """Open a regular asset by descriptor-walking from the film root."""
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise SceneSoundError("safe scene-sound source access is unavailable on this platform")
    try:
        directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise SceneSoundError("cannot safely open film root") from exc
    try:
        for part in relative.parts[:-1]:
            child_fd = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd
            )
            os.close(directory_fd)
            directory_fd = child_fd
        asset_fd = os.open(
            relative.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd
        )
    except OSError as exc:
        raise SceneSoundError("cannot safely open scene-sound asset") from exc
    finally:
        os.close(directory_fd)
    try:
        regular = stat.S_ISREG(os.fstat(asset_fd).st_mode)
    except OSError as exc:
        os.close(asset_fd)
        raise SceneSoundError("cannot safely inspect scene-sound asset") from exc
    if not regular:
        os.close(asset_fd)
        raise SceneSoundError("scene-sound source must be a regular file")
    return asset_fd


def _hash_fd(asset_fd: int) -> str:
    digest = hashlib.sha256()
    with ExitStack() as stack:
        source_fd = os.dup(asset_fd)
        stack.callback(os.close, source_fd)
        source = stack.enter_context(os.fdopen(source_fd, "rb", closefd=False))
        while block := source.read(1024 * 1024):
            digest.update(block)
    os.lseek(asset_fd, 0, os.SEEK_SET)
    return digest.hexdigest()


def _local_asset(root: Path, event: dict[str, Any], *, delivery_scope: str) -> tuple[Path, int]:
    source = str(event.get("source") or event.get("asset") or "")
    if source.startswith("library:"):
        from sfx_library import SFXLibraryError, default_library_root, resolve_uri

        try:
            library_root = default_library_root()
            path = resolve_uri(source, library_root=library_root)
            relative = path.relative_to(library_root)
            asset_root = library_root
        except (SFXLibraryError, ValueError) as exc:
            raise SceneSoundError(f"{event.get('id')}: library asset is invalid") from exc
        raw = source.removeprefix("library:")
    elif source.startswith("local:"):
        raw = source.removeprefix("local:")
        try:
            relative = (root / raw).relative_to(root)
        except ValueError as exc:
            raise SceneSoundError(f"{event.get('id')}: asset escapes film root") from exc
        path = root.joinpath(*relative.parts)
        asset_root = root
    else:
        raise SceneSoundError(
            f"{event.get('id')}: final only accepts local: or library: scene-sound assets"
        )
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise SceneSoundError(f"{event.get('id')}: asset escapes film root")
    asset_fd = _open_confined_asset(asset_root, relative)
    try:
        actual = _hash_fd(asset_fd)
        normalized_raw = raw.replace("\\", "/").lower()
        pending_candidate = (
            "/audio/candidates/" in f"/{normalized_raw}" and "/pending/" in f"/{normalized_raw}"
        )
        approved_internal = _approved_internal_sfx(
            root, event, path, actual, delivery_scope
        ) or _approved_internal_ambience(root, event, path, actual, delivery_scope)
        if (
            pending_candidate
            or is_noncommercial_license(event.get("license"))
            or is_candidate_only_license(event.get("license"))
            or event.get("production_eligible") is False
            or event.get("approval_status") == "pending_human_review"
        ) and not approved_internal:
            raise SceneSoundError(
                f"{event.get('id')}: non-commercial or pending candidate cannot enter a formal stem"
            )
        if (
            event.get("type") == "action_sfx"
            and not approved_internal
            and actual in _nonproduction_sfx_hashes(root)
        ):
            raise SceneSoundError(
                f"{event.get('id')}: known non-production SFX hash cannot enter a formal stem"
            )
        if actual != str(event.get("source_sha256") or ""):
            raise SceneSoundError(f"{event.get('id')}: asset checksum changed")
        if event.get("type") == "performance":
            _approved_performance(root, event, path, actual)
        return path, asset_fd
    except Exception:
        os.close(asset_fd)
        raise


def _stage_verified_asset(
    asset_fd: int, asset_label: str, expected_sha256: str, stage: Path
) -> int:
    """Return a verified temporary file descriptor, never a mutable source path."""
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise SceneSoundError("scene-sound asset checksum is invalid")
    target = stage / f"{hashlib.sha256(asset_label.encode()).hexdigest()}.wav"
    if target.exists() or target.is_symlink():
        raise SceneSoundError("scene-sound staging target already exists")
    if not hasattr(os, "O_NOFOLLOW"):
        raise SceneSoundError("safe scene-sound staging is unavailable on this platform")
    digest = hashlib.sha256()
    staged_fd: int | None = None
    try:
        with ExitStack() as stack:
            source_fd = os.dup(asset_fd)
            stack.callback(os.close, source_fd)
            source = stack.enter_context(os.fdopen(source_fd, "rb", closefd=False))
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise SceneSoundError("scene-sound source must be a regular file")
            target_fd = os.open(target, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            stack.callback(os.close, target_fd)
            output = stack.enter_context(os.fdopen(target_fd, "w+b", closefd=False))
            while block := source.read(1024 * 1024):
                digest.update(block)
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
            if digest.hexdigest() != expected_sha256:
                raise SceneSoundError("scene-sound asset changed during staging")
            staged_fd = os.dup(target_fd)
            os.lseek(staged_fd, 0, os.SEEK_SET)
            target.unlink()
    except SceneSoundError:
        if staged_fd is not None:
            os.close(staged_fd)
        raise
    except OSError as exc:
        if staged_fd is not None:
            os.close(staged_fd)
        raise SceneSoundError("cannot safely stage scene-sound asset") from exc
    finally:
        target.unlink(missing_ok=True)
    if staged_fd is None:
        raise SceneSoundError("cannot safely stage scene-sound asset")
    return staged_fd


def _write_stem(samples: np.ndarray, *, out: Path, sample_rate: int, label: str) -> dict[str, str]:
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "f32le",
                "-ar",
                str(sample_rate),
                "-ac",
                "2",
                "-i",
                "pipe:0",
                "-c:a",
                "pcm_s16le",
                str(out),
            ],
            input=np.clip(samples, -1.0, 1.0).tobytes(),
            capture_output=True,
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise SceneSoundError(f"cannot write {label} stem: ffmpeg timeout") from exc
    if proc.returncode:
        raise SceneSoundError(f"cannot write {label} stem")
    return {"path": str(out), "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}


def render_scene_sound_stem(
    root: Path,
    timeline: dict[str, Any],
    *,
    duration_sec: float,
    out: Path,
    sample_rate: int,
    ambience_out: Path | None = None,
) -> dict[str, Any]:
    """Render scene effects and ambience separately for director-controlled mixing."""
    shape = (max(1, int(round(duration_sec * sample_rate))), 2)
    samples = np.zeros(shape, dtype=np.float32)
    ambience_samples = np.zeros(shape, dtype=np.float32)
    executed: list[dict[str, Any]] = []
    delivery_scope = str(timeline.get("delivery_scope") or "commercial")
    asset_types = {"action_sfx", "ambience", "music", "performance"}
    with tempfile.TemporaryDirectory(prefix="aifilm-scene-sound-") as temporary:
        stage = Path(temporary)
        staged_assets: dict[tuple[str, str], int] = {}
        try:
            for event in timeline.get("events") or []:
                if (
                    not isinstance(event, dict)
                    or event.get("muted")
                    or event.get("type") not in asset_types
                ):
                    continue
                asset, source_fd = _local_asset(root, event, delivery_scope=delivery_scope)
                expected_sha256 = str(event.get("source_sha256") or "")
                key = (str(asset), expected_sha256)
                try:
                    if key not in staged_assets:
                        staged_assets[key] = _stage_verified_asset(
                            source_fd, str(asset), expected_sha256, stage
                        )
                finally:
                    os.close(source_fd)
                asset_fd = staged_assets[key]
                os.lseek(asset_fd, 0, os.SEEK_SET)
                duration = float(event["duration_sec"])
                try:
                    proc = subprocess.run(
                        [
                            "ffmpeg",
                            "-v",
                            "error",
                            "-stream_loop",
                            "-1",
                            "-i",
                            f"/dev/fd/{asset_fd}",
                            "-t",
                            f"{duration:.3f}",
                            "-ar",
                            str(sample_rate),
                            "-ac",
                            "2",
                            "-f",
                            "f32le",
                            "pipe:1",
                        ],
                        capture_output=True,
                        check=False,
                        pass_fds=(asset_fd,),
                        timeout=180,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise SceneSoundError(
                        f"{event.get('id')}: cannot decode asset: ffmpeg timeout"
                    ) from exc
                if proc.returncode:
                    raise SceneSoundError(f"{event.get('id')}: cannot decode asset")
                decoded = np.frombuffer(proc.stdout, dtype=np.float32).reshape((-1, 2))
                start = max(0, int(round(float(event["start_sec"]) * sample_rate)))
                end = min(len(samples), start + len(decoded))
                if end > start:
                    target = ambience_samples if event.get("type") == "ambience" else samples
                    target[start:end] += _apply_event_controls(
                        decoded[: end - start], event, sample_rate
                    )
                executed.append(
                    {
                        "id": event.get("id"),
                        "track": event.get("track"),
                        "stem": "ambience" if event.get("type") == "ambience" else "scene_sound",
                        "source": event.get("source"),
                        "executed": True,
                        "gain": event.get("gain", 1.0),
                        "pan": event.get("pan", 0.0),
                        "fade_in_sec": event.get("fade_in_sec", 0.0),
                        "fade_out_sec": event.get("fade_out_sec", 0.0),
                    }
                )
        finally:
            for asset_fd in staged_assets.values():
                os.close(asset_fd)
    scene_stem = _write_stem(samples, out=out, sample_rate=sample_rate, label="scene-sound")
    ambience_stem = (
        _write_stem(ambience_samples, out=ambience_out, sample_rate=sample_rate, label="ambience")
        if ambience_out is not None
        else None
    )
    return {
        **scene_stem,
        "event_count": len(executed),
        "events": executed,
        "ambience": {
            **(ambience_stem or {}),
            "event_count": sum(1 for event in executed if event["stem"] == "ambience"),
            "events": [event for event in executed if event["stem"] == "ambience"],
        },
    }
