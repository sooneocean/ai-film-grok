"""One-shot, fail-closed orchestration for budget-authorized film work."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from automation_verify import build_verification_report
from autopilot_notify import notify_telegram
from dispatch import build_dispatch
from dispatch_compact import compact_dispatch
from review_control import budget_status, load_settings, review_queue, runtime_status
from skill_runner import RUNNERS, run_autopilot_skill
from util import read_json, utc_now, write_json

AUTOPILOT_RECEIPT = "autopilot.json"
RESERVATIONS_RECEIPT = "autopilot-reservations.json"
_AUTOMATABLE_SKILLS = frozenset(
    {"keyframe.generate", "image.animate", "voice.synthesize", "video.render"}
)
# Wave W8 · local no-spend throughput next_ids that advance_local may execute.
# Single truth remains ADVANCE_ACTIONS; this set is the documented W8 contract
# (closeout / preflight / variety + related pack/shortlist/export/assist).
LOCAL_THROUGHPUT_NEXT_IDS = frozenset(
    {
        "closeout-run",
        "bulk-preflight",
        "variety-precheck",
        "i2v-motion-gate",
        "film-core-closeout",
        "pilot-pack",
        "select-shortlist",
        "ship-prep",
        "export-desktop",
        "agent-review-final",  # L0 assist only; advance rejects --apply
        "post-audit-gate",
        "selects-report",
        "audio-plan",
        "state-index-plan",
        "narrative-validate",
        "narrative-project",
        "production-evidence-gate",
        "write-spec",
        "quality-gate-repair",
        "dailies_review-evidence",
        "done",
    }
)
_BUDGET_STAGE = {
    "keyframe.generate": "still",
    "image.animate": "motion",
    "voice.synthesize": "audio",
    "video.render": "post",
}


class AutopilotError(ValueError):
    """The next dispatch action cannot safely be auto-executed."""


def _root(root: Path | str) -> Path:
    value = Path(root).expanduser().resolve()
    if not value.is_dir():
        raise AutopilotError("film root must be an existing directory")
    return value


def _payload_for_action(root: Path, action: dict[str, Any]) -> tuple[str, Path, dict[str, Any]]:
    argv = action.get("argv")
    if not isinstance(argv, list) or len(argv) != 6 or argv[:2] != ["skill", "run"]:
        raise AutopilotError("external action is not a fixed skill run")
    if argv[2] != "--skill-id" or argv[4] != "--payload-file":
        raise AutopilotError("external action has an unsafe skill-run shape")
    skill_id, path_text = str(argv[3]), str(argv[5])
    if skill_id not in _AUTOMATABLE_SKILLS or skill_id not in RUNNERS:
        raise AutopilotError("skill is not allowlisted for autopilot")
    path = Path(path_text).expanduser().resolve()
    if not path.is_file() or root not in path.parents:
        raise AutopilotError("payload file must be inside the film workspace")
    payload = read_json(path)
    if (
        not isinstance(payload, dict)
        or Path(str(payload.get("projectRoot") or "")).expanduser().resolve() != root
    ):
        raise AutopilotError("payload project root does not match the authoritative film root")
    return skill_id, path, payload


def _provider(payload: dict[str, Any]) -> str:
    values = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    return str(values.get("provider") or payload.get("provider") or "grok").strip().lower()


def _reservations_path(root: Path) -> Path:
    return root / "receipts" / RESERVATIONS_RECEIPT


def _active_reservations(root: Path, stage: str, spent: int) -> list[dict[str, Any]]:
    """Keep a requested budget reserved until accounting observes a later accepted cost."""
    value = read_json(_reservations_path(root)) or {}
    rows = value.get("reservations") if isinstance(value.get("reservations"), list) else []
    active = [
        item
        for item in rows
        if isinstance(item, dict)
        and item.get("stage") == stage
        and isinstance(item.get("requested_ticks"), int)
        and int(item.get("spent_before", spent)) >= spent
    ]
    retained = [
        item
        for item in rows
        if isinstance(item, dict) and (item.get("stage") != stage or item in active)
    ]
    if len(retained) != len(rows):
        write_json(
            _reservations_path(root),
            {
                "schema_version": 1,
                "kind": "aifilm-autopilot-reservations",
                "reservations": retained,
            },
        )
    return active


def _reserve(root: Path, *, transaction_id: str, budget: dict[str, Any]) -> None:
    path = _reservations_path(root)
    value = read_json(path) or {}
    rows = value.get("reservations") if isinstance(value.get("reservations"), list) else []
    if any(
        isinstance(item, dict) and item.get("transaction_id") == transaction_id for item in rows
    ):
        return
    rows.append({"transaction_id": transaction_id, "recorded_at": utc_now(), **budget})
    write_json(
        path, {"schema_version": 1, "kind": "aifilm-autopilot-reservations", "reservations": rows}
    )


def _budget_gate(root: Path, skill_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    stage = _BUDGET_STAGE[skill_id]
    scope = payload.get("spendScope")
    if not isinstance(scope, dict) or not isinstance(scope.get("budget"), dict):
        raise AutopilotError("external action requires an explicit spendScope budget")
    budget = scope["budget"]
    requested = budget.get("maxUnits")
    if isinstance(requested, bool) or not isinstance(requested, int) or requested <= 0:
        raise AutopilotError("spendScope budget maxUnits must be a positive integer USD tick count")
    if str(budget.get("currency") or "").strip().lower() not in {"usd_ticks", "usd-ticks"}:
        raise AutopilotError("autopilot only accepts USD-tick budget scopes")
    status = budget_status(root)
    spent = status["spent"].get(stage)
    remaining = status["remaining"].get(stage)
    envelope = status["envelopes"].get(stage, 0)
    if (
        not isinstance(spent, int)
        or not isinstance(remaining, int)
        or not isinstance(envelope, int)
    ):
        raise AutopilotError(f"{stage} cost is unknown")
    reserved = sum(
        int(item["requested_ticks"]) for item in _active_reservations(root, stage, spent)
    )
    available = remaining - reserved
    if envelope <= 0 or available < int(requested):
        raise AutopilotError(f"{stage} budget is exhausted or not configured")
    return {
        "stage": stage,
        "requested_ticks": int(requested),
        "spent_before": spent,
        "reserved_ticks": reserved,
        "status": status,
    }


def _provider_ready(root: Path, skill_id: str, provider: str) -> tuple[bool, str]:
    """Require a live, provider-specific route instead of accepting configured names."""
    try:
        if skill_id == "image.animate":
            from i2v_provider import get

            result = get(provider).probe(root=root)
            return bool(result.available), str(result.reason or "i2v provider unavailable")
        if skill_id == "keyframe.generate" and provider == "grok":
            from grok_oauth import probe

            result = probe()
            return bool(result.get("ok")), str(result.get("error") or "Grok auth unavailable")
        if skill_id == "voice.synthesize":
            from tts_backend import probe

            result = probe()
            return bool(result.get("ok")), str(result.get("error") or "TTS backend unavailable")
        if skill_id == "video.render":
            return True, "local render contract"
    except Exception as exc:  # noqa: BLE001 - this is a safety boundary
        return False, str(exc)[:200]
    return False, "provider/skill route is not verified"


def _sample_review_due(root: Path, every: int) -> str | None:
    """Require one approved review for each completed batch of ``every`` media jobs."""
    queue = read_json(root / "receipts" / "media-queue.json") or {}
    jobs = queue.get("jobs") if isinstance(queue.get("jobs"), list) else []
    completed = [job for job in jobs if isinstance(job, dict) and job.get("status") == "succeeded"]
    if not completed or len(completed) % every:
        return None
    shot_id = str(completed[-1].get("shot_id") or "")
    if not shot_id:
        return "unknown"
    states = {item["id"]: item["state"] for item in review_queue(root).get("items", [])}
    return None if states.get(f"shot:{shot_id}") == "approved" else shot_id


def _quality_gate(root: Path) -> dict[str, Any]:
    """Do not manufacture quality status for a project that has not been planned yet."""
    if not (root / "film-spec.json").is_file():
        return {"ok": True, "blocking_checks": []}
    return build_verification_report(root)


def _write(root: Path, report: dict[str, Any]) -> Path:
    target = root / "receipts" / AUTOPILOT_RECEIPT
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json(target, report)
    return target


def autopilot_once(
    root: Path | str,
    *,
    max_actions: int = 3,
    dry_run: bool = False,
    skill_executor: Callable[..., dict[str, Any]] = run_autopilot_skill,
    notifier: Callable[[str], dict[str, object]] = notify_telegram,
    provider_ready: Callable[[Path, str, str], tuple[bool, str]] = _provider_ready,
) -> dict[str, Any]:
    """Advance until a human, budget, readiness or quality boundary is reached."""
    base = _root(root)
    if max_actions < 1 or max_actions > 10:
        raise AutopilotError("max_actions must be between 1 and 10")
    settings = load_settings(base)
    policy = settings["autopilot"]
    executed: list[dict[str, Any]] = []
    seen_transactions: set[str] = set()
    stop_reason = "max_actions_reached"
    detail = ""
    lock_path = base / "receipts" / ".autopilot.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AutopilotError("another autopilot process already owns this project") from exc
        if not policy["enabled"]:
            stop_reason, detail = "autopilot_disabled", "enable it in review-control settings first"
        else:
            for _ in range(max_actions):
                queue = runtime_status(base)
                if queue["unknown"]:
                    stop_reason, detail = (
                        "queue_unknown",
                        "unknown queue work requires reconciliation",
                    )
                    break
                if queue["running"]:
                    stop_reason, detail = (
                        "queue_busy",
                        "running queue work must finish or reconcile first",
                    )
                    break
                sample_shot = _sample_review_due(base, int(policy["sample_every"]))
                if sample_shot is not None:
                    stop_reason = "sample_review_required"
                    detail = f"completed batch requires review for shot:{sample_shot}"
                    break
                packet = build_dispatch(base, include_capability=True, refresh_capability=True)
                action = (
                    packet.get("next_action")
                    if isinstance(packet.get("next_action"), dict)
                    else None
                )
                if action is None:
                    stop_reason = "no_executable_action"
                    break
                if (
                    action.get("approval_class") == "human_required"
                    and action.get("operation") != "skill"
                ):
                    stop_reason = "human_approval_required"
                    break
                if action.get("spend_class") == "local":
                    from advance import ADVANCE_ACTIONS, advance_local

                    next_id = str(packet.get("next_id") or "")
                    # W8: local path only for advance-allowlisted next_ids (fail closed).
                    if next_id not in ADVANCE_ACTIONS:
                        stop_reason = "local_not_allowlisted"
                        detail = f"local next_id not on advance allowlist: {next_id or '(empty)'}"
                        break
                    if dry_run:
                        # Never shell out on dry_run; plan only (mirrors external dry_run intent).
                        executed.append(
                            {
                                "kind": "local",
                                "dry_run": True,
                                "next_id": next_id,
                                "operation": action.get("operation"),
                                "w8_throughput": next_id in LOCAL_THROUGHPUT_NEXT_IDS,
                            }
                        )
                        continue
                    local = advance_local(base, max_local=1)
                    executed.append(
                        {
                            "kind": "local",
                            "next_id": next_id,
                            "w8_throughput": next_id in LOCAL_THROUGHPUT_NEXT_IDS,
                            "report": local,
                        }
                    )
                    if not local.get("ok") or local.get("executed_count") != 1:
                        stop_reason, detail = (
                            str(local.get("stop_reason")),
                            str(local.get("stop_detail") or ""),
                        )
                        break
                    quality = _quality_gate(base)
                    if not quality.get("ok"):
                        stop_reason = "quality_gate_failed"
                        detail = ",".join(
                            str(item) for item in quality.get("blocking_checks") or []
                        )
                        break
                    continue
                try:
                    skill_id, payload_path, payload = _payload_for_action(base, action)
                    action_transaction = str(action.get("transaction_id") or "")
                    if not action_transaction or action_transaction in seen_transactions:
                        raise AutopilotError("dispatch transaction is missing or already executed")
                    provider = _provider(payload)
                    if provider not in policy["allowed_providers"]:
                        raise AutopilotError("provider is not explicitly allowed for this project")
                    budget = _budget_gate(base, skill_id, payload)
                    ready, readiness_detail = provider_ready(base, skill_id, provider)
                    if not ready:
                        raise AutopilotError(f"provider readiness failed: {readiness_detail}")
                except AutopilotError as exc:
                    stop_reason, detail = "external_safety_gate", str(exc)
                    break
                if dry_run:
                    result = skill_executor(skill_id, payload_path, dry_run=True)
                else:
                    result = skill_executor(skill_id, payload_path, dry_run=False)
                    if result.get("ok"):
                        _reserve(base, transaction_id=action_transaction, budget=budget)
                seen_transactions.add(action_transaction)
                executed.append(
                    {
                        "kind": "external",
                        "skill_id": skill_id,
                        "provider": provider,
                        "budget": budget,
                        "result": result,
                    }
                )
                if not result.get("ok"):
                    stop_reason, detail = "external_action_failed", str(result.get("error") or "")
                    break
                quality = _quality_gate(base)
                if not quality.get("ok"):
                    stop_reason = "quality_gate_failed"
                    detail = ",".join(str(item) for item in quality.get("blocking_checks") or [])
                    break
            else:
                stop_reason = "max_actions_reached"
        quality = _quality_gate(base)
        packet = build_dispatch(base, include_capability=False, write_receipt=False)
        report: dict[str, Any] = {
            "schema_version": 1,
            "kind": "aifilm-autopilot",
            "root": str(base),
            "checked_at": utc_now(),
            "dry_run": dry_run,
            "ok": stop_reason not in {"external_action_failed"},
            "executed": executed,
            "stop_reason": stop_reason,
            "stop_detail": detail,
            "budget": budget_status(base),
            "quality": quality,
            "next": compact_dispatch(packet),
        }
        if policy["telegram_notify"] and stop_reason != "max_actions_reached":
            report["notification"] = notifier(
                f"AI Film autopilot paused: {stop_reason}. {detail or 'Open the review console for next action.'}"
            )
        else:
            report["notification"] = {"attempted": False, "ok": False, "reason": "not_needed"}
        report["receipt"] = str(_write(base, report))
        return report
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
