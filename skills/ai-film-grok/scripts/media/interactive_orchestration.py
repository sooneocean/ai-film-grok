"""Recoverable cloud-candidate queue; approvals stay in ``approval_ledger``."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from media_qa import MediaQAError, analyze_media
from security_policy import SecurityPolicyError, safe_existing_file, validate_identifier
from util import exclusive_file_lock, read_json, sha256_file, utc_now, write_json

STATE_NAME = "interactive-orchestration.json"
_MEDIA_SUFFIXES = frozenset({".mp4", ".mov", ".m4v", ".webm"})
_ERROR_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
_FRW_QUERY_OPERATIONS = frozenset(
    {
        "newvideo-query",
        "text2video-query",
        "img2video-query",
        "img2video-audio-query",
        "flf-query",
    }
)


class InteractiveOrchestrationError(ValueError):
    """The cloud candidate contract cannot safely advance."""


def _root(root: Path | str) -> Path:
    value = Path(root).expanduser().resolve()
    if not value.is_dir():
        raise InteractiveOrchestrationError("film root must be an existing directory")
    return value


def _path(root: Path) -> Path:
    return root / "receipts" / STATE_NAME


def _empty() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "interactive-orchestration",
        "revision": 0,
        "candidates": [],
    }


def _load(root: Path) -> dict[str, Any]:
    value = read_json(_path(root))
    if not isinstance(value, dict) or value.get("kind") != "interactive-orchestration":
        return _empty()
    candidates = value.get("candidates")
    if not isinstance(candidates, list):
        raise InteractiveOrchestrationError("interactive candidate state is invalid")
    value["candidates"] = [item for item in candidates if isinstance(item, dict)]
    value.setdefault("revision", 0)
    return value


def _write(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    state["revision"] = int(state.get("revision") or 0) + 1
    state["updated_at"] = utc_now()
    write_json(_path(root), state)
    return state


def _candidate(state: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for item in state["candidates"]:
        if item.get("id") == candidate_id:
            return item
    raise InteractiveOrchestrationError("cloud candidate does not exist")


def _cloud_capability(root: Path, capability_id: str) -> dict[str, Any]:
    snapshot = read_json(root / "receipts" / "capability-snapshot.json")
    if not isinstance(snapshot, dict):
        raise InteractiveOrchestrationError("capability snapshot is required")
    matches = [
        item
        for item in snapshot.get("capabilities") or []
        if isinstance(item, dict) and item.get("id") == capability_id
    ]
    if len(matches) != 1:
        raise InteractiveOrchestrationError("cloud capability is not present exactly once")
    capability = matches[0]
    if str(capability.get("provider") or "").lower() not in {"frw", "grok"}:
        raise InteractiveOrchestrationError("only FRW and Grok cloud candidates are enabled")
    if str(capability.get("resource") or "").lower() != "cloud":
        raise InteractiveOrchestrationError("capability is not an enabled cloud resource")
    if (
        capability.get("status") != "ready"
        or capability.get("authorization") != "ready"
        or capability.get("pilot_verified") is not True
    ):
        raise InteractiveOrchestrationError("cloud capability is not ready and verified")
    return capability


def submit_cloud_candidate(
    root: Path | str,
    *,
    candidate_id: str,
    shot_id: str,
    capability_id: str,
    task_id: str,
    query_operation: str | None = None,
) -> dict[str, Any]:
    """Register an already-submitted adapter task without sending provider requests."""
    base = _root(root)
    candidate_id = validate_identifier(candidate_id, field="candidate id")
    shot_id = validate_identifier(shot_id, field="shot id")
    capability_id = validate_identifier(capability_id, field="capability id")
    task_id = validate_identifier(task_id, field="task id")
    capability = _cloud_capability(base, capability_id)
    if query_operation is not None:
        if query_operation not in _FRW_QUERY_OPERATIONS:
            raise InteractiveOrchestrationError("unsupported FRW query operation")
        if str(capability["provider"]).lower() != "frw":
            raise InteractiveOrchestrationError("only FRW candidates use a CLI query operation")
    with exclusive_file_lock(_path(base)):
        state = _load(base)
        existing = next(
            (item for item in state["candidates"] if item.get("id") == candidate_id), None
        )
        payload = {
            "id": candidate_id,
            "shot_id": shot_id,
            "capability_id": capability_id,
            "provider": capability["provider"],
            "model": capability["model"],
            "resource": "cloud",
            "task_id": task_id,
            "status": "submitted",
            "submitted_at": utc_now(),
        }
        if query_operation is not None:
            payload["query_operation"] = query_operation
        if existing is not None:
            binding = ("shot_id", "capability_id", "task_id", "query_operation")
            if {key: existing.get(key) for key in binding} != {
                key: payload.get(key) for key in binding
            }:
                raise InteractiveOrchestrationError("candidate id is already bound to another task")
            return state
        state["candidates"].append(payload)
        return _write(base, state)


def _provider_payload(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def poll_frw_candidate(
    root: Path | str, *, candidate_id: str, download: bool = False
) -> dict[str, Any]:
    """Poll a submitted FRW task through its stable query CLI contract.

    This performs no generation or download.  It deliberately retains only
    the normalized task state/error code; media still enters through the
    workspace-only terminal-media gate.
    """
    base = _root(root)
    candidate_id = validate_identifier(candidate_id, field="candidate id")
    with exclusive_file_lock(_path(base)):
        state = _load(base)
        candidate = dict(_candidate(state, candidate_id))
    if str(candidate.get("provider") or "").lower() != "frw":
        raise InteractiveOrchestrationError("only FRW has a standalone polling adapter")
    operation = candidate.get("query_operation")
    if operation not in _FRW_QUERY_OPERATIONS:
        raise InteractiveOrchestrationError("FRW candidate has no approved query operation")
    dispatch = Path(__file__).resolve().parent.parent / "frw_dispatch.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(dispatch), str(operation), "--task-id", str(candidate["task_id"])],
            capture_output=True,
            text=True,
            timeout=75,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InteractiveOrchestrationError("FRW polling adapter could not run") from exc
    payload = _provider_payload(proc.stdout)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    error_code = data.get("error_code")
    normalized = {
        "protocol_version": payload.get("protocol_version"),
        "done": payload.get("done") is True,
        "success": payload.get("success") is True,
        "next_action": payload.get("next_action"),
        "error_code": error_code if isinstance(error_code, str) else None,
        "returncode": proc.returncode,
    }
    downloaded: dict[str, object] | None = None
    download_error: str | None = None
    if normalized["done"] and normalized["success"] and download:
        media_url = data.get("video_url") or data.get("url")
        if not isinstance(media_url, str):
            download_error = "DOWNLOAD_URL_MISSING"
        else:
            try:
                from cloud_media_download import CloudMediaDownloadError, download_cloud_video

                downloaded = download_cloud_video(base, candidate_id=candidate_id, url=media_url)
            except CloudMediaDownloadError:
                download_error = "DOWNLOAD_FAILED"
    with exclusive_file_lock(_path(base)):
        state = _load(base)
        stored = _candidate(state, candidate_id)
        stored["last_poll"] = normalized
        stored["last_polled_at"] = utc_now()
        if normalized["error_code"] and _ERROR_CODE_RE.fullmatch(normalized["error_code"]):
            stored.update(
                status="failed", error_code=normalized["error_code"], terminal_at=utc_now()
            )
        elif proc.returncode != 0 or not payload:
            stored.update(status="failed", error_code="RUNTIME_ERROR", terminal_at=utc_now())
        elif download_error:
            stored.update(
                status="download_failed", error_code=download_error, terminal_at=utc_now()
            )
        elif downloaded is not None:
            stored.update(status="downloaded", downloaded=downloaded, terminal_at=utc_now())
        elif normalized["done"] and normalized["success"]:
            stored["status"] = "awaiting_terminal_media"
        result = _write(base, state)
    return result


def record_terminal_media(
    root: Path | str, *, candidate_id: str, media_path: str
) -> dict[str, Any]:
    """Accept only a previously staged, decoded workspace video for human review."""
    base = _root(root)
    candidate_id = validate_identifier(candidate_id, field="candidate id")
    raw_media = Path(media_path).expanduser()
    unresolved_media = raw_media if raw_media.is_absolute() else base / raw_media
    if unresolved_media.is_symlink():
        raise InteractiveOrchestrationError("cloud candidate media may not be a symbolic link")
    try:
        media = safe_existing_file(base, media_path, field="cloud candidate media")
    except SecurityPolicyError as exc:
        raise InteractiveOrchestrationError(str(exc)) from exc
    if media.suffix.lower() not in _MEDIA_SUFFIXES:
        raise InteractiveOrchestrationError("cloud candidate media must be a workspace video")
    try:
        qa = analyze_media(
            media,
            require_audio=False,
            require_motion=False,
            min_width=704,
            min_height=1280,
        )
    except MediaQAError as exc:
        raise InteractiveOrchestrationError("cloud candidate media QA failed") from exc
    if qa.get("ok") is not True or qa.get("decode_ok") is not True:
        raise InteractiveOrchestrationError("cloud candidate media did not pass decode QA")
    relative = str(media.relative_to(base))
    receipt = {
        "kind": "interactive-cloud-candidate-media",
        "candidate_id": candidate_id,
        "media_path": relative,
        "media_sha256": sha256_file(media),
        "technical_qa": qa,
        "recorded_at": utc_now(),
    }
    receipt_path = base / "receipts" / "interactive-candidates" / f"{candidate_id}.json"
    write_json(receipt_path, receipt)
    with exclusive_file_lock(_path(base)):
        state = _load(base)
        candidate = _candidate(state, candidate_id)
        if candidate.get("status") not in {"awaiting_terminal_media", "downloaded"}:
            raise InteractiveOrchestrationError(
                "cloud candidate has not completed its provider/download lifecycle"
            )
        candidate.update(
            status="reviewable",
            media_path=relative,
            media_sha256=receipt["media_sha256"],
            receipt_path=str(receipt_path.relative_to(base)),
            receipt_sha256=sha256_file(receipt_path),
            technical_qa={
                key: qa.get(key)
                for key in (
                    "ok",
                    "decode_ok",
                    "duration_sec",
                    "width",
                    "height",
                    "min_width",
                    "min_height",
                    "has_audio",
                    "errors",
                )
            },
            terminal_at=utc_now(),
        )
        result = _write(base, state)
    # A missing review UI or Telegram configuration is a non-fatal notification
    # condition; the durable reviewable receipt remains the source of work.
    from autopilot_notify import notify_review_ready

    notification = notify_review_ready(
        str(base),
        shot_id=str(candidate["shot_id"]),
        provider=str(candidate["provider"]),
        model=str(candidate["model"]),
    )
    result["notification"] = notification
    return result


def record_task_failure(root: Path | str, *, candidate_id: str, error_code: str) -> dict[str, Any]:
    base = _root(root)
    candidate_id = validate_identifier(candidate_id, field="candidate id")
    if not isinstance(error_code, str) or not _ERROR_CODE_RE.fullmatch(error_code):
        raise InteractiveOrchestrationError("a stable provider error code is required")
    with exclusive_file_lock(_path(base)):
        state = _load(base)
        candidate = _candidate(state, candidate_id)
        candidate.update(status="failed", error_code=error_code, terminal_at=utc_now())
        return _write(base, state)


def queue_status(root: Path | str) -> dict[str, Any]:
    state = _load(_root(root))
    candidates = [dict(item) for item in state["candidates"]]
    reviewable = sorted(
        item["shot_id"] for item in candidates if item.get("status") == "reviewable"
    )
    return {
        "revision": state["revision"],
        "candidates": candidates,
        "next_reviewable_shot": reviewable[0] if reviewable else None,
    }


def assert_review_action_allowed(
    root: Path | str, *, stage: str, action: str, candidate_id: str | None = None
) -> None:
    if not stage.startswith("shot:") or action != "approve":
        return
    shot_id = stage.removeprefix("shot:")
    candidates = [
        item for item in queue_status(root)["candidates"] if item.get("shot_id") == shot_id
    ]
    if not candidates:
        return
    if not candidate_id:
        raise InteractiveOrchestrationError("select a terminal-media reviewable cloud candidate")
    candidate_id = validate_identifier(candidate_id, field="candidate id")
    selected = next((item for item in candidates if item.get("id") == candidate_id), None)
    if selected is None or selected.get("status") != "reviewable":
        raise InteractiveOrchestrationError(
            "selected cloud candidate is not terminal-media reviewable"
        )


def note_review_action(
    root: Path | str, *, stage: str, action: str, candidate_id: str | None = None
) -> None:
    if not stage.startswith("shot:"):
        return
    base = _root(root)
    path = _path(base)
    if not path.is_file():
        return
    with exclusive_file_lock(path):
        state = _load(base)
        for candidate in state["candidates"]:
            if candidate.get("id") == candidate_id:
                candidate["last_review_action"] = action
                candidate["last_reviewed_at"] = utc_now()
        _write(base, state)
