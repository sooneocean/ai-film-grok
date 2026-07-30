#!/usr/bin/env python3
"""Private, frame-only multimodal review sidecar.

The adapter accepts only explicitly declared sanitized still frames within a
film workspace.  Its output is advisory evidence for a human reviewer; it
cannot approve a shot, modify a manifest, select a provider, or submit media.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import math
import os
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
from local_llm import (
    LocalLLMError,
    _request_json,
    _safe_usage,
    normalize_base_url,
)
from security_policy import safe_existing_file

DEFAULT_MODEL = "nvidia/nemotron-nano-3-30b-a3b"
MAX_SAFE_FRAMES = 5
MAX_FRAME_BYTES = 8 * 1024 * 1024
MAX_FRAME_INDEX_BYTES = 64 * 1024
REPORT_NAME = "local-omni-review.json"
_IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["issues"],
    "properties": {
        "issues": {
            "type": "array",
            "maxItems": MAX_SAFE_FRAMES,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["frame_index", "code", "note"],
                "properties": {
                    "frame_index": {"type": "integer", "minimum": 0, "maximum": 4},
                    "code": {"type": "string", "minLength": 1, "maxLength": 64},
                    "note": {"type": "string", "minLength": 1, "maxLength": 500},
                },
            },
        }
    },
}


class LocalOmniReviewError(ValueError):
    """A private review request did not meet its source or response contract."""


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _redact_token_echo(value: str, token: str | None) -> str:
    return value.replace(token, "[REDACTED]") if token else value


def _read_regular_file(path: Path, *, limit: int, label: str) -> bytes:
    """Bind validation and bounded reading to one non-symlink file descriptor."""
    if not hasattr(os, "O_NOFOLLOW"):
        raise LocalOmniReviewError(f"platform cannot safely read {label}")
    try:
        file_fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise LocalOmniReviewError(f"{label} must remain a regular non-symlink file") from exc
    try:
        metadata = os.fstat(file_fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise LocalOmniReviewError(f"{label} must remain a regular non-symlink file")
        if metadata.st_size > limit:
            raise LocalOmniReviewError(f"{label} exceeds its review size limit")
        with os.fdopen(file_fd, "rb") as handle:
            file_fd = -1
            raw = handle.read(limit + 1)
    finally:
        if file_fd >= 0:
            os.close(file_fd)
    if len(raw) > limit:
        raise LocalOmniReviewError(f"{label} exceeds its review size limit")
    return raw


def _read_frame(path: Path) -> bytes:
    return _read_regular_file(path, limit=MAX_FRAME_BYTES, label="sanitized frame")


def _workspace_frame(root: Path, value: str) -> Path:
    raw = Path(value).expanduser()
    unresolved = raw if raw.is_absolute() else root / raw
    if unresolved.is_symlink():
        raise LocalOmniReviewError("sanitized frame must be a regular non-symlink file")
    try:
        frame = safe_existing_file(root, unresolved, field="sanitized frame")
    except Exception as exc:
        message = str(exc)
        if "escapes" in message:
            raise LocalOmniReviewError("sanitized frame must be inside the film workspace") from exc
        raise LocalOmniReviewError(
            "sanitized frame must be a regular file inside the film workspace"
        ) from exc
    if frame.suffix.lower() not in _IMAGE_SUFFIXES:
        raise LocalOmniReviewError("sanitized frame must be a png, jpg, or webp image")
    if frame.stat().st_size > MAX_FRAME_BYTES:
        raise LocalOmniReviewError("sanitized frame exceeds the 8 MiB review limit")
    return frame


def _load_frames(root: Path, frame_index: Path | str) -> list[dict[str, Any]]:
    raw_index = Path(frame_index).expanduser()
    unresolved = raw_index if raw_index.is_absolute() else root / raw_index
    if unresolved.is_symlink():
        raise LocalOmniReviewError("sanitized frame index must be a regular non-symlink file")
    try:
        index = safe_existing_file(root, unresolved, field="sanitized frame index")
        payload = json.loads(
            _read_regular_file(
                index,
                limit=MAX_FRAME_INDEX_BYTES,
                label="sanitized frame index",
            )
        )
    except Exception as exc:
        raise LocalOmniReviewError(
            "sanitized frame index must be valid JSON inside the film workspace"
        ) from exc
    entries = payload.get("frames") if isinstance(payload, dict) else payload
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_SAFE_FRAMES:
        raise LocalOmniReviewError(f"sanitized frame index must list 1-{MAX_SAFE_FRAMES} frames")
    frames: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise LocalOmniReviewError("sanitized frame index entries need path and timestamp_sec")
        timestamp = item.get("timestamp_sec")
        if (
            type(timestamp) not in {int, float}
            or not math.isfinite(float(timestamp))
            or timestamp < 0
        ):
            raise LocalOmniReviewError(
                "sanitized frame timestamp_sec must be a non-negative number"
            )
        path = _workspace_frame(root, item["path"])
        before_sha = hashlib.sha256(_read_frame(path)).hexdigest()
        frames.append(
            {
                "path": path,
                "relative_path": str(path.relative_to(root)),
                "timestamp_sec": round(float(timestamp), 3),
                "sha256": before_sha,
            }
        )
    return frames


def _image_part(frame: dict[str, Any]) -> dict[str, Any]:
    path = Path(frame["path"])
    raw = _read_frame(path)
    if hashlib.sha256(raw).hexdigest() != frame["sha256"]:
        raise LocalOmniReviewError("sanitized frame changed while preparing the private review")
    mime = {".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower(), "image/jpeg")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"},
    }


def _assert_frames_unchanged(frames: list[dict[str, Any]]) -> None:
    if any(
        hashlib.sha256(_read_frame(Path(frame["path"]))).hexdigest() != frame["sha256"]
        for frame in frames
    ):
        raise LocalOmniReviewError("sanitized frame changed during the private review")


def _write_report(root: Path, report: dict[str, Any], frames: list[dict[str, Any]]) -> Path:
    """Atomically replace a report through the opened, non-symlink receipts directory."""
    receipts = root / "receipts"
    if receipts.is_symlink():
        raise LocalOmniReviewError("review receipts directory must not be a symbolic link")
    receipts.mkdir(parents=False, exist_ok=True)
    if not all(hasattr(os, name) for name in ("O_DIRECTORY", "O_NOFOLLOW")):
        raise LocalOmniReviewError("platform cannot safely write private review reports")
    directory_fd: int | None = None
    temporary_name: str | None = None
    try:
        directory_fd = os.open(receipts, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        _assert_frames_unchanged(frames)
        temporary_name = f".{REPORT_NAME}.{next(tempfile._get_candidate_names())}.tmp"
        file_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        with os.fdopen(file_fd, "wb") as handle:
            handle.write((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, REPORT_NAME, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        temporary_name = None
        try:
            _assert_frames_unchanged(frames)
        except LocalOmniReviewError:
            os.unlink(REPORT_NAME, dir_fd=directory_fd)
            raise
    except OSError as exc:
        raise LocalOmniReviewError("could not safely write local omni review report") from exc
    finally:
        if temporary_name is not None and directory_fd is not None:
            with contextlib.suppress(OSError):
                os.unlink(temporary_name, dir_fd=directory_fd)
        if directory_fd is not None:
            os.close(directory_fd)
    return receipts / REPORT_NAME


def probe(base_url: str, *, model: str = DEFAULT_MODEL, token: str | None = None) -> dict[str, Any]:
    """Read the private model list only; never start multimodal inference."""
    if not isinstance(model, str) or not model.strip() or len(model) > 200:
        raise LocalOmniReviewError("local omni model id is invalid")
    try:
        normalized = normalize_base_url(base_url)
        response = _request_json(normalized, "/models", token=token, timeout=10)
    except LocalLLMError as exc:
        raise LocalOmniReviewError(f"{exc.code}: {exc}") from exc
    models = response.get("data")
    ids = sorted(
        _redact_token_echo(item["id"], token)
        for item in (models if isinstance(models, list) else [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    )
    return {
        "schema_version": 1,
        "kind": "local-omni-review-probe",
        "base_url": normalized,
        "model": model,
        "available_models": ids,
        "model_available": model in ids,
        "ok": model in ids,
        "inference_started": False,
        "fallback": "human review and existing deterministic QA; no automatic retry",
    }


def review_frames(
    root: Path | str,
    base_url: str,
    *,
    frame_index: Path | str,
    model: str = DEFAULT_MODEL,
    token: str | None = None,
    sanitized: bool = False,
    timeout: int = 60,
) -> dict[str, Any]:
    """Write a hash-bound candidate report from declared private technical frames."""
    if not sanitized:
        raise LocalOmniReviewError("local omni review requires explicit --sanitized declaration")
    if not isinstance(model, str) or not model.strip() or len(model) > 200:
        raise LocalOmniReviewError("local omni model id is invalid")
    if timeout < 1 or timeout > 120:
        raise LocalOmniReviewError("timeout must be between 1 and 120 seconds")
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise LocalOmniReviewError("film root must exist")
    try:
        normalized = normalize_base_url(base_url)
    except LocalLLMError as exc:
        raise LocalOmniReviewError(f"{exc.code}: {exc}") from exc
    frames = _load_frames(base, frame_index)
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Act only as a private film-review sidecar. Inspect only these declared sanitized "
                "technical frames. Return JSON {issues:[{frame_index,code,note}]}. Flag only visible "
                "subtitle obstruction, black/frozen frames, obvious continuity drift, or visual defects. "
                "Every issue is a candidate for a human reviewer; never claim approval or give creative instructions."
            ),
        }
    ]
    content.extend(_image_part(frame) for frame in frames)
    try:
        response = _request_json(
            normalized,
            "/chat/completions",
            token=token,
            timeout=timeout,
            body={
                "model": model,
                "temperature": 0,
                "max_tokens": 700,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "private_frame_review",
                        "strict": True,
                        "schema": _RESPONSE_SCHEMA,
                    },
                },
                "messages": [
                    {"role": "system", "content": "Return only the strict JSON review schema."},
                    {"role": "user", "content": content},
                ],
            },
        )
    except LocalLLMError as exc:
        raise LocalOmniReviewError(f"{exc.code}: {exc}") from exc
    _assert_frames_unchanged(frames)
    choices = response.get("choices")
    choice = (
        choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    )
    if choice.get("finish_reason") != "stop":
        raise LocalOmniReviewError("private omni review did not finish normally")
    message = choice.get("message")
    content_value = message.get("content") if isinstance(message, dict) else None
    try:
        candidate = json.loads(content_value) if isinstance(content_value, str) else None
        Draft202012Validator(_RESPONSE_SCHEMA).validate(candidate)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise LocalOmniReviewError("private omni review did not return valid review JSON") from exc
    findings = [
        {
            "code": _redact_token_echo(item["code"], token),
            "severity": "candidate",
            "timestamp_sec": frames[item["frame_index"]]["timestamp_sec"],
            "note": _redact_token_echo(item["note"], token),
        }
        for item in candidate["issues"]
        if item["frame_index"] < len(frames)
    ]
    if len(findings) != len(candidate["issues"]):
        raise LocalOmniReviewError(
            "private omni review referenced a frame outside the submitted index"
        )
    report = {
        "schema_version": 1,
        "kind": "local-omni-review",
        "at": _utc_now(),
        "status": "candidate_only",
        "base_url": normalized,
        "model": model,
        "candidate_findings": findings,
        "inputs": {
            "sanitized_frames": [
                {key: frame[key] for key in ("relative_path", "timestamp_sec", "sha256")}
                for frame in frames
            ]
        },
        "sanitized_technical_inputs": True,
        "usage": _safe_usage(response.get("usage")),
        "may_approve_production": False,
        "may_change_provider": False,
        "may_submit_generation": False,
        "human_review_required": True,
        "fallback": "human review and existing deterministic QA; no automatic retry",
    }
    output = _write_report(base, report, frames)
    report["path"] = str(output)
    return report
