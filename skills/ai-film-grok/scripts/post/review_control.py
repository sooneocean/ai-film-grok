"""Hash-bound review queue and local-control decisions for the review UI.

This module deliberately does not invent a second approval truth.  It stores
operator notes as receipts and writes approvals through ``approval_ledger``.
"""

from __future__ import annotations

import re
from contextlib import suppress
from math import isfinite
from pathlib import Path
from typing import Any

from approval_ledger import (
    ApprovalLedgerConflict,
    append_approval,
    approval_is_current,
    read_approval_ledger,
)
from pipeline_events import append_event
from util import exclusive_file_lock, read_json, sha256_file, utc_now, write_json

SETTINGS_NAME = "review-control.json"
ACTION_NAME = "review-actions.json"
AUTOPILOT_NAME = "autopilot.json"
STAGES = (
    ("story", "故事与导演合约", ("drama-graph.json", "film-spec.json")),
    ("design", "视觉设计与资产", ("style-bible.json", "assets.json")),
    ("budget", "成本与生成队列", ("production-book.json", "receipts/media-queue.json")),
    ("pilot", "Pilot 审核", ("receipts/pilot-scorecard.json", "receipts/pilot-approval.json")),
    ("audio", "声音与混音", ("receipts/tts-rehearsal.json", "receipts/mix_report.json")),
    ("preview", "预览与粗剪", ("receipts/compose-preview.json", "receipts/rough-cut.json")),
    ("final", "终片审片", ("manifest.json", "out/final-review.json")),
)
VALID_ACTIONS = frozenset({"approve", "reject", "reshoot", "needs_changes"})
VALID_ISSUES = frozenset(
    {
        "story",
        "continuity",
        "identity",
        "composition",
        "motion",
        "audio",
        "subtitle",
        "technical",
        "budget",
        "other",
    }
)
_STAGE_RE = re.compile(
    r"^(?:story|design|budget|pilot|audio|preview|final|"
    r"director:(?:concept_lock|script_lock|department_look_lock|shot_animatic_lock|"
    r"pilot_approval|bulk|dailies_review|selects_rough_cut|picture_lock|post_locks|"
    r"master_lock)|shot:[A-Za-z0-9_.-]+)$"
)
_SHOT_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class ReviewControlError(ValueError):
    """A UI request violates the review-control contract."""


class ReviewControlConflict(ReviewControlError):
    """The browser acted on an outdated revision."""


def _root(root: Path | str) -> Path:
    value = Path(root).expanduser().resolve()
    if not value.is_dir():
        raise ReviewControlError("film root must be an existing directory")
    return value


def _safe_stage(stage: str) -> str:
    if not _STAGE_RE.fullmatch(stage):
        raise ReviewControlError("unknown review stage")
    return stage


def _settings_path(root: Path) -> Path:
    return root / "receipts" / SETTINGS_NAME


def _actions_path(root: Path) -> Path:
    return root / "receipts" / ACTION_NAME


def _default_settings() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "review-control-settings",
        "revision": 0,
        "reviewer": "owner",
        "budget_envelopes": {"still": 0, "motion": 0, "audio": 0, "post": 0},
        "advance_mode": "next_review_gate",
        "autopilot": {
            "enabled": False,
            "sample_every": 5,
            "allowed_providers": [],
            "telegram_notify": True,
        },
    }


def load_settings(root: Path | str) -> dict[str, Any]:
    value = read_json(_settings_path(_root(root)))
    if not isinstance(value, dict):
        return _default_settings()
    default = _default_settings()
    default.update(value)
    envelopes = value.get("budget_envelopes")
    if isinstance(envelopes, dict):
        default["budget_envelopes"] = {
            key: max(0, int(envelopes.get(key, 0))) for key in default["budget_envelopes"]
        }
    autopilot = value.get("autopilot")
    if isinstance(autopilot, dict):
        default["autopilot"] = {
            "enabled": bool(autopilot.get("enabled", False)),
            "sample_every": max(1, int(autopilot.get("sample_every", 5))),
            "allowed_providers": sorted(
                {
                    str(item).strip()
                    for item in autopilot.get("allowed_providers", [])
                    if isinstance(item, str) and item.strip()
                }
            ),
            "telegram_notify": bool(autopilot.get("telegram_notify", True)),
        }
    return default


def update_settings(
    root: Path | str,
    *,
    expected_revision: int,
    reviewer: str | None = None,
    budget_envelopes: dict[str, Any] | None = None,
    autopilot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = _root(root)
    path = _settings_path(base)
    with exclusive_file_lock(path):
        current = load_settings(base)
        if int(current["revision"]) != expected_revision:
            raise ReviewControlConflict("review settings revision is stale")
        if reviewer is not None:
            reviewer = reviewer.strip()
            if not reviewer or len(reviewer) > 80:
                raise ReviewControlError("reviewer must be 1-80 characters")
            current["reviewer"] = reviewer
        if budget_envelopes is not None:
            if set(budget_envelopes) - set(current["budget_envelopes"]):
                raise ReviewControlError("unknown budget envelope")
            for key, value in budget_envelopes.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                    raise ReviewControlError("budget values must be non-negative numbers")
                current["budget_envelopes"][key] = int(value)
        if autopilot is not None:
            if set(autopilot) - {"enabled", "sample_every", "allowed_providers", "telegram_notify"}:
                raise ReviewControlError("unknown autopilot setting")
            merged = dict(current["autopilot"])
            merged.update(autopilot)
            allowed = merged["allowed_providers"]
            if not isinstance(allowed, list):
                raise ReviewControlError("autopilot allowed_providers must be a list")
            current["autopilot"] = {
                "enabled": bool(merged["enabled"]),
                "sample_every": max(1, int(merged["sample_every"])),
                "allowed_providers": sorted(
                    {
                        str(item).strip()
                        for item in allowed
                        if isinstance(item, str) and item.strip()
                    }
                ),
                "telegram_notify": bool(merged["telegram_notify"]),
            }
        current["revision"] = int(current["revision"]) + 1
        current["updated_at"] = utc_now()
        write_json(path, current)
        return current


def _hashes(root: Path, relpaths: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for relative in relpaths:
        path = (root / relative).resolve()
        if path.is_file() and root in path.parents and not path.is_symlink():
            result[relative] = sha256_file(path)
    return result


def _shot_items(root: Path) -> list[tuple[str, str, tuple[str, ...]]]:
    manifest = read_json(root / "manifest.json") or {}
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    stills = manifest.get("stills") if isinstance(manifest.get("stills"), dict) else {}
    ids = sorted(
        shot_id
        for shot_id in ({str(key) for key in clips} | {str(key) for key in stills})
        if _SHOT_ID_RE.fullmatch(shot_id)
    )
    items: list[tuple[str, str, tuple[str, ...]]] = []
    for shot_id in ids:
        candidates = ["manifest.json", f"receipts/reviews/{shot_id}.json"]
        for record in (stills.get(shot_id), clips.get(shot_id)):
            if isinstance(record, dict) and isinstance(record.get("path"), str):
                candidate = Path(record["path"])
                if candidate.is_absolute():
                    with suppress(ValueError):
                        candidates.append(str(candidate.resolve().relative_to(root)))
        items.append((f"shot:{shot_id}", f"镜头 {shot_id}", tuple(candidates)))
    return items


def _stage_state(
    ledger: dict[str, Any], stage: str, hashes: dict[str, str]
) -> tuple[str, str | None]:
    approvals = ledger.get("approvals") if isinstance(ledger.get("approvals"), list) else []
    matches = [
        item
        for item in approvals
        if isinstance(item, dict)
        and item.get("scope") == f"review:{stage}"
        and item.get("approval_type") == "review_gate"
        and item.get("revoked") is not True
    ]
    if not matches:
        return ("blocked" if not hashes else "pending_review"), None
    latest = matches[-1]
    if latest.get("ledger_integrity_current") is not True:
        return "stale", str(latest.get("approval_id"))
    if latest.get("project_binding_current") is not True:
        return "stale", str(latest.get("approval_id"))
    current = approval_is_current(latest, hashes)
    if current["ok"]:
        return "approved", str(latest.get("approval_id"))
    return "stale", str(latest.get("approval_id"))


def review_queue(root: Path | str) -> dict[str, Any]:
    base = _root(root)
    ledger = read_approval_ledger(base)
    actions = _load_actions(base)
    from interactive_orchestration import queue_status

    cloud = queue_status(base)
    items: list[dict[str, Any]] = []
    for stage, title, paths in [*STAGES, *_shot_items(base)]:
        hashes = _hashes(base, paths)
        state, approval_id = _stage_state(ledger, stage, hashes)
        items.append(
            {
                "id": stage,
                "title": title,
                "state": state,
                "approval_id": approval_id,
                "input_hashes": hashes,
                "evidence_refs": sorted(hashes),
                "recent_actions": _recent_actions(actions, stage),
                "media": [
                    path
                    for path in hashes
                    if Path(path).suffix.lower()
                    in {".mp4", ".mov", ".wav", ".mp3", ".png", ".jpg", ".jpeg"}
                ],
            }
        )
    for item in items:
        if not item["id"].startswith("shot:"):
            continue
        shot_id = item["id"].removeprefix("shot:")
        candidates = [row for row in cloud["candidates"] if row.get("shot_id") == shot_id]
        item["cloud_candidates"] = [
            {
                key: row.get(key)
                for key in (
                    "id",
                    "provider",
                    "model",
                    "task_id",
                    "status",
                    "error_code",
                    "media_path",
                    "receipt_path",
                    "technical_qa",
                )
            }
            for row in candidates
        ]
        bound_paths = tuple(
            str(row[key])
            for row in candidates
            if row.get("status") == "reviewable"
            for key in ("media_path", "receipt_path")
            if isinstance(row.get(key), str)
        )
        if bound_paths:
            extra_hashes = _hashes(base, bound_paths)
            item["input_hashes"].update(extra_hashes)
            item["evidence_refs"] = sorted(item["input_hashes"])
            item["media"] = sorted(
                set(item["media"])
                | {
                    path
                    for path in extra_hashes
                    if Path(path).suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}
                }
            )
    book = read_json(base / "production-book.json") or {}
    if book.get("rigor") == "professional":
        from director_cli import validate_native_stage_evidence
        from director_stage_gates import STAGE_ORDER, stage_status

        director = stage_status(base)
        current = director.get("next_stage")
        if current in STAGE_ORDER:
            try:
                refs = validate_native_stage_evidence(base, str(current))
                hashes = _hashes(base, tuple(refs.values()))
                state = "pending_review"
            except ValueError:
                refs, hashes, state = {}, {}, "blocked"
            items.insert(
                0,
                {
                    "id": f"director:{current}",
                    "title": f"Professional stage: {current}",
                    "state": state,
                    "approval_id": None,
                    "input_hashes": hashes,
                    "evidence_refs": sorted(hashes),
                    "recent_actions": _recent_actions(actions, f"director:{current}"),
                    "media": [],
                },
            )
    return {
        "kind": "review-queue",
        "ledger_revision": ledger["revision"],
        "items": items,
        "cloud": {"next_reviewable_shot": cloud["next_reviewable_shot"]},
        "budget": budget_status(base),
        "runtime": runtime_status(base),
    }


def budget_status(root: Path | str) -> dict[str, Any]:
    """Show only locally recorded cost counters; unknown is never treated as zero."""
    base = _root(root)
    settings = load_settings(base)
    usage = read_json(base / "receipts" / "generation-usage.json") or {}
    spent: dict[str, int | None] = {key: 0 for key in settings["budget_envelopes"]}
    operation_stage = {
        "t2i": "still",
        "image_edit": "still",
        "i2v": "motion",
        "t2v": "motion",
        "tts": "audio",
    }
    for event in usage.get("events") if isinstance(usage.get("events"), list) else []:
        if not isinstance(event, dict) or event.get("phase") != "accepted":
            continue
        stage = operation_stage.get(str(event.get("operation") or ""))
        value = (
            (event.get("usage") or {}).get("cost_in_usd_ticks")
            if isinstance(event.get("usage"), dict)
            else None
        )
        if stage and isinstance(value, int) and value >= 0 and spent[stage] is not None:
            spent[stage] = int(spent[stage] or 0) + value
        elif stage:
            spent[stage] = None
    envelopes = settings["budget_envelopes"]
    return {
        "envelopes": envelopes,
        "spent": spent,
        "remaining": {
            key: None if spent[key] is None else max(0, envelopes[key] - spent[key])
            for key in envelopes
        },
    }


def runtime_status(root: Path | str) -> dict[str, Any]:
    """Expose sanitized queue state so pending/unknown work is visibly non-approvable."""
    base = _root(root)
    queue = read_json(base / "receipts" / "media-queue.json") or {}
    jobs = queue.get("jobs") if isinstance(queue.get("jobs"), list) else []
    counts: dict[str, int] = {}
    for job in jobs:
        if isinstance(job, dict):
            status = str(job.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
    return {
        "job_counts": counts,
        "running": sum(
            value for key, value in counts.items() if key in {"running", "claimed", "submitted"}
        ),
        "unknown": counts.get("unknown", 0),
    }


def autopilot_status(root: Path | str) -> dict[str, Any] | None:
    """Return the latest non-secret autopilot receipt, if one exists."""
    value = read_json(_root(root) / "receipts" / AUTOPILOT_NAME)
    return value if isinstance(value, dict) else None


def _load_actions(root: Path) -> dict[str, Any]:
    value = read_json(_actions_path(root))
    return (
        value
        if isinstance(value, dict)
        else {"schema_version": 1, "kind": "review-actions", "revision": 0, "actions": []}
    )


def _recent_actions(actions: dict[str, Any], stage: str, *, limit: int = 3) -> list[dict[str, Any]]:
    """Return a small, schema-checked decision trail without exposing raw receipts."""
    values = actions.get("actions")
    if not isinstance(values, list):
        return []
    result: list[dict[str, Any]] = []
    for event in reversed(values):
        if len(result) >= limit:
            break
        if not isinstance(event, dict) or event.get("stage") != stage:
            continue
        action = event.get("action")
        issue = event.get("issue")
        note = event.get("note")
        recorded_at = event.get("recorded_at")
        timestamp_sec = event.get("timestamp_sec")
        if (
            action not in VALID_ACTIONS
            or issue not in VALID_ISSUES
            or not isinstance(note, str)
            or not 0 < len(note) <= 4000
            or not isinstance(recorded_at, str)
            or not 0 < len(recorded_at) <= 80
        ):
            continue
        if timestamp_sec is not None and (
            isinstance(timestamp_sec, bool)
            or not isinstance(timestamp_sec, (int, float))
            or not isfinite(timestamp_sec)
            or timestamp_sec < 0
            or timestamp_sec > 86_400
        ):
            continue
        result.append(
            {
                "action": action,
                "issue": issue,
                "note": note,
                "timestamp_sec": timestamp_sec,
                "recorded_at": recorded_at,
            }
        )
    return result


def record_action(
    root: Path | str,
    *,
    stage: str,
    action: str,
    issue: str,
    note: str,
    timestamp_sec: float | None,
    expected_ledger_revision: int,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    base = _root(root)
    stage = _safe_stage(stage)
    if action not in VALID_ACTIONS or issue not in VALID_ISSUES:
        raise ReviewControlError("invalid review action or issue category")
    note = note.strip()
    if not note or len(note) > 4000:
        raise ReviewControlError("review note is required and must be under 4000 characters")
    if timestamp_sec is not None and (
        isinstance(timestamp_sec, bool)
        or not isinstance(timestamp_sec, (int, float))
        or not isfinite(timestamp_sec)
        or timestamp_sec < 0
        or timestamp_sec > 86_400
    ):
        raise ReviewControlError("timestamp must be a valid non-negative second offset")
    ledger = read_approval_ledger(base)
    if int(ledger["revision"]) != expected_ledger_revision:
        raise ReviewControlConflict("approval ledger revision is stale")
    queue = review_queue(base)
    item = next((value for value in queue["items"] if value["id"] == stage), None)
    if item is None or not item["input_hashes"]:
        raise ReviewControlError("review item has no current local evidence")
    from interactive_orchestration import (
        InteractiveOrchestrationError,
        assert_review_action_allowed,
        note_review_action,
    )

    try:
        assert_review_action_allowed(base, stage=stage, action=action, candidate_id=candidate_id)
    except InteractiveOrchestrationError as exc:
        raise ReviewControlError(str(exc)) from exc
    event = {
        "stage": stage,
        "action": action,
        "issue": issue,
        "note": note,
        "timestamp_sec": timestamp_sec,
        "input_hashes": item["input_hashes"],
        "recorded_at": utc_now(),
    }
    if candidate_id is not None:
        event["candidate_id"] = candidate_id
    if action == "approve":
        if stage.startswith("director:"):
            director_stage = stage.split(":", 1)[1]
            try:
                from director_cli import lock_native_stage

                locked = lock_native_stage(
                    base,
                    stage=director_stage,
                    approver=load_settings(base)["reviewer"],
                    user_phrase=note,
                    expected_ledger_revision=expected_ledger_revision,
                    transaction_id=f"review-ui:{stage}:{item['input_hashes']}",
                )
            except (ApprovalLedgerConflict, ValueError) as exc:
                raise ReviewControlConflict(str(exc)) from exc
            event["approval_id"] = locked["approval_id"]
            event["stage_lock"] = locked["lock"]
        else:
            try:
                approval = append_approval(
                    base,
                    expected_revision=expected_ledger_revision,
                    scope=f"review:{stage}",
                    approval_type="review_gate",
                    approver_type="human",
                    approver=load_settings(base)["reviewer"],
                    authorization_event={
                        "source": "review-ui",
                        "action": "approve",
                        "stage": stage,
                        "candidate_id": candidate_id,
                    },
                    input_hashes=item["input_hashes"],
                    evidence_refs=item["evidence_refs"],
                    transaction_id=f"review-ui:{stage}:{item['input_hashes']}",
                )
            except ApprovalLedgerConflict as exc:
                raise ReviewControlConflict(str(exc)) from exc
            event["approval_id"] = approval["approval_id"]
    path = _actions_path(base)
    with exclusive_file_lock(path):
        actions = _load_actions(base)
        actions["revision"] = int(actions["revision"]) + 1
        actions["actions"].append(event)
        write_json(path, actions)
    append_event(
        base,
        stage=f"review:{stage}",
        phase="completed" if action == "approve" else "failed",
        note=issue,
    )
    note_review_action(base, stage=stage, action=action, candidate_id=candidate_id)
    return {"ok": True, "event": event, "queue": review_queue(base)}


def advance_to_next_review(root: Path | str, *, expected_ledger_revision: int) -> dict[str, Any]:
    """Run only pre-existing allowlisted local work and stop at the next review boundary."""
    base = _root(root)
    if int(read_approval_ledger(base)["revision"]) != expected_ledger_revision:
        raise ReviewControlConflict("approval ledger revision is stale")
    try:
        from review_mode_policy import ReviewModeError, assert_review_advance_allowed

        assert_review_advance_allowed(base)
    except ReviewModeError as exc:
        raise ReviewControlError(str(exc)) from exc
    queue = review_queue(base)
    runtime = queue["runtime"]
    if runtime["running"] or runtime["unknown"]:
        raise ReviewControlError("running or unknown provider work blocks automatic advance")
    from advance import advance_local

    return advance_local(base, max_local=3)
