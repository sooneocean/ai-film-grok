"""No-spend 30–60 second benchmark contract for the dialogue weapon chain."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import secrets
import stat
from pathlib import Path
from typing import Any

import dialogue_scene_package
from util import utc_now

MIN_DURATION_SEC = 30.0
MAX_DURATION_SEC = 60.0
WEAPONS = (
    "comfy_qwen_i2i_performance_state",
    "comfy_qwen_i2i_keyframe",
    "frw_ltx23_img2video_audio",
)
WEAPON_EXECUTORS = {
    "comfy_qwen_i2i_performance_state": "comfy",
    "comfy_qwen_i2i_keyframe": "comfy",
    "frw_ltx23_img2video_audio": "frw",
}
_PACKAGE_NAME = "dialogue-scene-package.json"
_REPORT_NAME = "dialogue-weapon-benchmark.json"
_MAX_PACKAGE_BYTES = 4 * 1024 * 1024


def _open_benchmark_root(root: Path | str) -> tuple[Path, int]:
    raw_root = Path(root).expanduser()
    base = Path(os.path.abspath(raw_root))
    if raw_root.is_symlink() or not all(
        hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")
    ):
        raise ValueError("BENCHMARK_ROOT_INVALID")
    try:
        root_fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise ValueError("BENCHMARK_ROOT_INVALID") from exc
    return base, root_fd


def _read_package(root_fd: int) -> object:
    try:
        file_fd = os.open(
            _PACKAGE_NAME,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=root_fd,
        )
    except OSError as exc:
        raise ValueError("BENCHMARK_PACKAGE_UNSAFE") from exc
    try:
        before = os.fstat(file_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or before.st_size > _MAX_PACKAGE_BYTES
        ):
            raise ValueError("BENCHMARK_PACKAGE_UNSAFE")
        chunks = bytearray()
        while chunk := os.read(file_fd, min(1024 * 1024, _MAX_PACKAGE_BYTES + 1 - len(chunks))):
            chunks.extend(chunk)
            if len(chunks) > _MAX_PACKAGE_BYTES:
                break
        raw = bytes(chunks)
        after = os.fstat(file_fd)
        if (
            len(raw) > _MAX_PACKAGE_BYTES
            or len(raw) != before.st_size
            or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        ):
            raise ValueError("BENCHMARK_PACKAGE_UNSAFE")
        return json.loads(raw)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("BENCHMARK_PACKAGE_UNSAFE") from exc
    finally:
        os.close(file_fd)


def _write_report(root_fd: int, report: dict[str, Any]) -> None:
    receipts_fd: int | None = None
    temporary_name: str | None = None
    try:
        try:
            receipts_fd = os.open(
                "receipts",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=root_fd,
            )
        except FileNotFoundError:
            with contextlib.suppress(FileExistsError):
                os.mkdir("receipts", mode=0o700, dir_fd=root_fd)
            receipts_fd = os.open(
                "receipts",
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=root_fd,
            )
        try:
            metadata = os.stat(_REPORT_NAME, dir_fd=receipts_fd, follow_symlinks=False)
        except FileNotFoundError:
            metadata = None
        if metadata is not None and stat.S_ISLNK(metadata.st_mode):
            raise ValueError("BENCHMARK_RECEIPT_PATH_UNSAFE")
        temporary_name = f".{_REPORT_NAME}.{secrets.token_hex(8)}.tmp"
        file_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=receipts_fd,
        )
        with os.fdopen(file_fd, "wb") as handle:
            handle.write((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary_name,
            _REPORT_NAME,
            src_dir_fd=receipts_fd,
            dst_dir_fd=receipts_fd,
        )
        temporary_name = None
        os.fsync(receipts_fd)
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError("BENCHMARK_RECEIPT_PATH_UNSAFE") from exc
    finally:
        if temporary_name is not None and receipts_fd is not None:
            with contextlib.suppress(OSError):
                os.unlink(temporary_name, dir_fd=receipts_fd)
        if receipts_fd is not None:
            os.close(receipts_fd)


def _build_dialogue_benchmark(base: Path, root_fd: int, package: object) -> dict[str, Any]:
    validation = dialogue_scene_package.validate_dialogue_scene_package(package)
    package_object = package if isinstance(package, dict) else {}
    lines = [
        line
        for scene in package_object.get("scenes") or []
        if isinstance(scene, dict)
        for line in scene.get("lines") or []
        if isinstance(line, dict)
    ]
    selected: list[dict[str, Any]] = []
    duration = 0.0
    invalid_audio_evidence = False
    for line in lines:
        audio = line.get("audio") if isinstance(line.get("audio"), dict) else {}
        try:
            line_duration = float(audio.get("duration_sec") or 0)
        except (TypeError, ValueError):
            line_duration = 0.0
        if line_duration <= 0:
            continue
        if not dialogue_scene_package.validate_audio_evidence(audio, root=base):
            invalid_audio_evidence = True
            continue
        if duration + line_duration > MAX_DURATION_SEC and selected:
            break
        selected.append({"line_id": line.get("line_id"), "duration_sec": line_duration})
        duration += line_duration
        if duration >= MIN_DURATION_SEC:
            break
    blockers: list[dict[str, str]] = []
    if not validation.get("ok"):
        blockers.append({"code": "DIALOGUE_PACKAGE_INVALID", "message": "repair package first"})
    if invalid_audio_evidence:
        blockers.append(
            {
                "code": "BENCHMARK_AUDIO_EVIDENCE_INVALID",
                "message": "selected dialogue audio lacks safe measured media evidence",
            }
        )
    if duration < MIN_DURATION_SEC:
        blockers.append(
            {
                "code": "BENCHMARK_DURATION_INSUFFICIENT",
                "message": "need 30–60 seconds of measured dialogue rehearsal audio",
            }
        )
    report = {
        "schema_version": 1,
        "kind": "dialogue-weapon-benchmark",
        "created_at": utc_now(),
        "status": "planned" if not blockers else "blocked",
        "duration_sec": round(duration, 3),
        "line_ids": [row["line_id"] for row in selected],
        "weapons": list(WEAPONS),
        "arms": [
            {"weapon": weapon, "status": "pending", "human_review_required": True}
            for weapon in WEAPONS
        ],
        "selection": {
            "status": "pending_human_review",
            "require_same_lines": True,
            "require_stable_parameter_choice": True,
        },
        "blockers": blockers,
    }
    path = base / "receipts" / _REPORT_NAME
    _write_report(root_fd, report)
    report["receipt"] = str(path)
    return report


def build_dialogue_benchmark(root: Path | str) -> dict[str, Any]:
    """Create a fixed, no-spend benchmark once real rehearsal audio exists."""
    base, root_fd = _open_benchmark_root(root)
    try:
        package = _read_package(root_fd)
        return _build_dialogue_benchmark(base, root_fd, package)
    finally:
        os.close(root_fd)


def _read_report(root_fd: int) -> dict[str, Any]:
    receipts_fd = os.open("receipts", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
    try:
        fd = os.open(_REPORT_NAME, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=receipts_fd)
        try:
            meta = os.fstat(fd)
            if not stat.S_ISREG(meta.st_mode) or meta.st_size > _MAX_PACKAGE_BYTES:
                raise ValueError("BENCHMARK_RECEIPT_PATH_UNSAFE")
            value = json.loads(os.read(fd, _MAX_PACKAGE_BYTES + 1))
        finally:
            os.close(fd)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("DIALOGUE_BENCHMARK_NOT_PLANNED") from exc
    finally:
        os.close(receipts_fd)
    if not isinstance(value, dict) or value.get("status") != "planned":
        raise ValueError("DIALOGUE_BENCHMARK_NOT_PLANNED")
    return value


def _sha256_file(path: Path) -> str:
    """Hash a review artifact without loading a video into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def record_benchmark_arm(
    root: Path | str,
    *,
    weapon: str,
    artifact: Path | str,
    reviewer: str,
    note: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Register one real, human-reviewed arm without promoting it to production."""
    base, root_fd = _open_benchmark_root(root)
    try:
        report = _read_report(root_fd)
        media = Path(artifact).expanduser().resolve()
        if (
            weapon not in WEAPONS
            or not media.is_file()
            or not media.is_relative_to(base)
            or not reviewer.strip()
            or not note.strip()
        ):
            raise ValueError("BENCHMARK_ARM_INPUT_INVALID")
        arm = next((item for item in report["arms"] if item.get("weapon") == weapon), None)
        if not isinstance(arm, dict):
            raise ValueError("BENCHMARK_ARM_INPUT_INVALID")
        artifact_sha256 = _sha256_file(media)
        stable_parameters = dict(parameters)
        if weapon == "frw_ltx23_img2video_audio":
            from native_text_gate import validate_native_text_review

            review = stable_parameters.get("native_text_review")
            if not isinstance(review, dict):
                raise ValueError("LTX_NATIVE_TEXT_REVIEW_REQUIRED")
            review = {**review, "clip_sha256": artifact_sha256}
            native_text_gate = validate_native_text_review(review)
            if not native_text_gate.get("ok"):
                raise ValueError(str(native_text_gate.get("reason") or "LTX_NATIVE_TEXT_REJECTED"))
            stable_parameters["native_text_review"] = review
        arm.update(
            {
                "status": "reviewed",
                "artifact": str(media.relative_to(base)),
                "artifact_sha256": artifact_sha256,
                "reviewer": reviewer.strip(),
                "review_note": note.strip(),
                "stable_parameters": stable_parameters,
            }
        )
        # A changed arm invalidates both the prior parameter selection and its
        # signature; it must receive an explicit fresh human approval.
        report.pop("receipt_hmac_sha256", None)
        if (report.get("selection") or {}).get("status") == "approved":
            report["selection"] = {
                "status": "pending_human_review",
                "require_same_lines": True,
                "require_stable_parameter_choice": True,
            }
        _write_report(root_fd, report)
        return report
    finally:
        os.close(root_fd)


def approve_benchmark_parameters(
    root: Path | str, *, reviewer: str, rationale: str
) -> dict[str, Any]:
    """Lock stable parameters for every stage after all human reviews."""
    _base, root_fd = _open_benchmark_root(root)
    try:
        report = _read_report(root_fd)
        if any(
            not isinstance(arm, dict) or arm.get("status") != "reviewed" for arm in report["arms"]
        ):
            raise ValueError("BENCHMARK_ALL_ARMS_REVIEW_REQUIRED")
        if not reviewer.strip() or not rationale.strip():
            raise ValueError("BENCHMARK_SELECTION_INVALID")
        report["selection"] = {
            "status": "approved",
            "reviewer": reviewer.strip(),
            "rationale": rationale.strip(),
            "required_weapons": list(WEAPONS),
            "stable_parameters": {
                str(arm["weapon"]): dict(arm.get("stable_parameters") or {})
                for arm in report["arms"]
                if isinstance(arm, dict)
            },
        }
        try:
            from performance_candidates import PerformanceCandidateError, sign_receipt

            sign_receipt(report)
        except (ImportError, PerformanceCandidateError) as exc:
            raise ValueError("BENCHMARK_RECEIPT_SIGNING_REQUIRED") from exc
        _write_report(root_fd, report)
        return report
    finally:
        os.close(root_fd)
