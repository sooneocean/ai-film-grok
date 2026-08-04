#!/usr/bin/env python3
"""Fail-closed execution of a very small set of local dispatch actions."""

from __future__ import annotations

import fcntl
import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dispatch import bind_action_to_state, build_dispatch, structured_next_action
from dispatch_compact import compact_dispatch, compute_state_hash
from transaction_receipt import (
    TransactionConflict,
    begin_receipt,
    complete_receipt,
    load_receipt,
    stable_hash,
)

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SECRET = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+|((?:api[_-]?key|token|secret)=)\S+")
_MAX_LOCAL_HARD = 10


@dataclass(frozen=True)
class AdvancePolicy:
    skill_ids: tuple[str, ...]
    prefix: tuple[str, ...]
    value_flags: tuple[str, ...] = ("--root",)
    bool_flags: tuple[str, ...] = ()
    verifier: tuple[str, ...] = ()


ADVANCE_ACTIONS: dict[str, AdvancePolicy] = {
    "concept_lock-evidence": AdvancePolicy(
        ("dispatch.orchestrate",),
        ("plan", "status"),
        verifier=("plan", "status"),
    ),
    "write-spec": AdvancePolicy(
        ("dispatch.orchestrate", "shot.plan"),
        ("write-spec",),
        verifier=("preflight",),
    ),
    "narrative-validate": AdvancePolicy(
        ("story.validate",),
        ("plan", "validate"),
        bool_flags=("--strict",),
        verifier=("plan", "validate", "--strict"),
    ),
    "narrative-project": AdvancePolicy(
        ("graph.project",),
        ("graph", "project"),
        bool_flags=("--force",),
        verifier=("graph", "validate"),
    ),
    "state-index-plan": AdvancePolicy(
        ("character.state.update",),
        ("state-index", "plan"),
        verifier=("state-index", "check"),
    ),
    "production-evidence-gate": AdvancePolicy(
        ("projection.verify",),
        ("production-evidence",),
        verifier=("production-evidence",),
    ),
    "post-audit-gate": AdvancePolicy(
        ("projection.verify",),
        ("post-audit",),
        verifier=("post-audit",),
    ),
    # Wave F · throughput cmds (local + approval none)
    "closeout-run": AdvancePolicy(
        ("projection.verify", "dispatch.orchestrate"),
        ("closeout", "run"),
        verifier=("closeout", "status"),
    ),
    "bulk-preflight": AdvancePolicy(
        ("image.animate", "projection.verify", "dispatch.orchestrate"),
        ("bulk-preflight",),
        bool_flags=("--no-tunnel", "--no-lease"),
        verifier=("bulk-preflight",),
    ),
    "variety-precheck": AdvancePolicy(
        ("story.validate", "dispatch.orchestrate"),
        ("variety-precheck",),
        verifier=("variety-precheck",),
    ),
    "i2v-motion-gate": AdvancePolicy(
        ("projection.verify", "dispatch.orchestrate"),
        ("i2v-motion-gate",),
        value_flags=("--root",),
        bool_flags=("--write",),
        verifier=("i2v-motion-gate",),
    ),
    "film-core-closeout": AdvancePolicy(
        ("projection.verify", "dispatch.orchestrate"),
        ("closeout", "status"),
        verifier=("closeout", "status"),
    ),
    "pilot-pack": AdvancePolicy(
        ("quality.inspect", "dispatch.orchestrate"),
        ("pilot-pack",),
        verifier=("pilot-pack",),
    ),
    "select-shortlist": AdvancePolicy(
        ("projection.verify", "dispatch.orchestrate"),
        ("select-shortlist",),
        verifier=("select-shortlist",),
    ),
    "ship-prep": AdvancePolicy(
        ("projection.verify", "dispatch.orchestrate"),
        ("ship-prep",),
        value_flags=("--root",),
        bool_flags=("--no-measure", "--no-promote", "--skip-variety"),
        verifier=("ship-prep",),
    ),
    # P0: post-audit green + final_complete → local desktop package (no artistic approve).
    "export-desktop": AdvancePolicy(
        ("export.package", "dispatch.orchestrate"),
        ("export-desktop",),
        value_flags=("--root", "--name"),
        verifier=("status",),
    ),
    # P1: L0 assist draft for review-final (never --approve).
    "agent-review-final": AdvancePolicy(
        ("quality.inspect", "dispatch.orchestrate"),
        ("agent-review-final",),
        value_flags=("--root", "--reviewer", "--notes", "--human-minutes"),
        bool_flags=("--no-assist-input",),
        verifier=("agent-review-final",),
    ),
    "quality-gate-repair": AdvancePolicy(
        ("dispatch.orchestrate",),
        ("preflight",),
        verifier=("preflight",),
    ),
    "selects-report": AdvancePolicy(
        ("projection.verify",),
        ("selects",),
        bool_flags=("--no-write",),
        verifier=("selects",),
    ),
    "dailies_review-evidence": AdvancePolicy(
        ("dispatch.orchestrate",),
        ("dailies", "status"),
        verifier=("dailies", "status"),
    ),
    "rough-cut-review": AdvancePolicy(
        ("dispatch.orchestrate",),
        ("editor-cut",),
        verifier=("editor-cut",),
    ),
    "department_look_lock-evidence": AdvancePolicy(
        ("dispatch.orchestrate",),
        ("director", "status"),
        verifier=("director", "status"),
    ),
    "audio-plan": AdvancePolicy(
        ("sound.design",),
        ("audio-plan",),
        verifier=("audio-plan",),
    ),
    "done": AdvancePolicy(
        ("dispatch.orchestrate",),
        ("status",),
        verifier=("status",),
    ),
}


class AdvanceError(ValueError):
    """A dispatch action is unsafe, stale or not authorized for local advance."""


def _redact(text: str) -> str:
    return _SECRET.sub(lambda match: (match.group(1) or match.group(2) or "") + "[REDACTED]", text)


def _safe_env() -> dict[str, str]:
    env = {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", ""),
        "PYTHONNOUSERSITE": "1",
    }
    return {key: value for key, value in env.items() if value}


def _sanitize_result(result: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(result)
    for field in ("stdout", "stderr"):
        if field in sanitized:
            sanitized[field] = _redact(str(sanitized.get(field) or "")[-4000:])
    return sanitized


def _validate_argv(
    *,
    root: Path,
    action_id: str,
    action: dict[str, Any],
) -> tuple[AdvancePolicy, list[str]]:
    policy = ADVANCE_ACTIONS.get(action_id)
    if policy is None:
        raise AdvanceError(f"action is not allowlisted for local advance: {action_id}")
    if action.get("spend_class") != "local" or action.get("approval_class") != "none":
        raise AdvanceError("packet policy is not local + approval-free")
    skill_id = str(action.get("skill_id") or "")
    if skill_id not in policy.skill_ids:
        raise AdvanceError("action skill_id does not match the advance policy")
    raw_argv = action.get("argv")
    if not isinstance(raw_argv, list) or not all(isinstance(item, str) for item in raw_argv):
        raise AdvanceError("action argv must be a string array")
    argv = list(raw_argv)
    if any(_CONTROL.search(item) for item in argv):
        raise AdvanceError("action argv contains control characters")
    if tuple(argv[: len(policy.prefix)]) != policy.prefix:
        raise AdvanceError("action argv prefix does not match the advance policy")

    tail = argv[len(policy.prefix) :]
    seen_root = 0
    index = 0
    while index < len(tail):
        token = tail[index]
        if token in policy.bool_flags:
            index += 1
            continue
        if token not in policy.value_flags or index + 1 >= len(tail):
            raise AdvanceError(f"unknown or incomplete advance flag: {token}")
        value = tail[index + 1]
        if token == "--root":
            seen_root += 1
            if Path(value).expanduser().resolve() != root:
                raise AdvanceError("action root does not match the authoritative project root")
        index += 2
    if seen_root != 1:
        raise AdvanceError("action must contain exactly one authoritative --root")
    return policy, argv


def _run_fixed(argv: list[str], *, timeout_sec: int = 600) -> dict[str, Any]:
    script = Path(__file__).with_name("aifilm_grok.py").resolve()
    python = Path(sys.executable).resolve()
    process = subprocess.run(
        [str(python), str(script), *argv],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
        shell=False,
        env=_safe_env(),
    )
    stdout = _redact(process.stdout[-4000:])
    stderr = _redact(process.stderr[-4000:])
    return {
        "ok": process.returncode == 0,
        "returncode": process.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def _verification_argv(policy: AdvancePolicy, root: Path) -> list[str]:
    if not policy.verifier:
        raise AdvanceError("advance policy has no fixed verifier")
    return [*policy.verifier, "--root", str(root)]


def _verify_action(
    *,
    policy: AdvancePolicy,
    root: Path,
    argv: list[str],
    action_result: dict[str, Any],
    run: Callable[[list[str]], dict[str, Any]],
) -> dict[str, Any]:
    """Run the fixed verifier unless the successful action already was that check."""
    verifier_argv = _verification_argv(policy, root)
    if argv == verifier_argv:
        return action_result
    return _sanitize_result(run(verifier_argv))


def _expected_transaction(
    *,
    root: Path,
    state_hash: str,
    next_id: str,
    action: dict[str, Any],
) -> str:
    rebound = bind_action_to_state(
        structured_next_action(
            {
                "id": next_id,
                "cmd": "aifilm " + " ".join(str(item) for item in action.get("argv") or []),
            },
            context={
                "node_refs": action.get("node_refs") or [],
                "input_hashes": action.get("input_hashes") or {},
                "dependencies": action.get("dependencies") or [],
                "expected_outputs": action.get("expected_outputs") or [],
                "verification": action.get("verification") or [],
            },
        ),
        root=root,
        state_hash=state_hash,
    )
    if rebound is None:
        raise AdvanceError("action cannot be reconstructed safely")
    return str(rebound["transaction_id"])


def advance_local(
    root: Path,
    *,
    gates: dict[str, Any] | None = None,
    open_reshoot_count: int = 0,
    max_local: int = 3,
    runner: Callable[[list[str]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute allowlisted local steps; stop on every approval or uncertainty boundary."""
    root = Path(root).expanduser().resolve()
    if max_local < 1 or max_local > _MAX_LOCAL_HARD:
        raise AdvanceError(f"max_local must be between 1 and {_MAX_LOCAL_HARD}")
    if not root.is_dir():
        raise AdvanceError("film root must already exist")
    lock_path = root / "receipts" / ".advance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AdvanceError("another advance process already owns this project") from exc

        run = runner or _run_fixed
        executed: list[dict[str, Any]] = []
        seen_transactions: set[str] = set()
        seen_actions: set[str] = set()
        stop_reason = "max_local_reached"
        stop_detail = ""
        full_packet: dict[str, Any] | None = None
        for _ in range(max_local):
            full_packet = build_dispatch(
                root,
                gates=gates,
                open_reshoot_count=open_reshoot_count,
                include_capability=False,
                write_receipt=True,
                use_state_cache=False,
            )
            action = (
                full_packet.get("next_action")
                if isinstance(full_packet.get("next_action"), dict)
                else None
            )
            if action is None:
                stop_reason = "no_executable_action"
                break
            if action.get("approval_class") == "human_required":
                stop_reason = "human_approval_required"
                break
            if action.get("spend_class") != "local":
                stop_reason = "paid_or_external"
                break

            next_id = str(full_packet.get("next_id") or "")
            try:
                policy, argv = _validate_argv(
                    root=root,
                    action_id=next_id,
                    action=action,
                )
            except AdvanceError as exc:
                stop_reason = "unsafe_or_unknown_action"
                stop_detail = str(exc)
                break
            action_signature = stable_hash({"next_id": next_id, "argv": argv})
            if action_signature in seen_actions:
                stop_reason = "cycle_detected"
                break
            seen_actions.add(action_signature)
            planned_state = str(full_packet.get("state_hash") or "")
            current_state = compute_state_hash(
                root,
                gates=gates,
                open_reshoot_count=open_reshoot_count,
            )
            if planned_state != current_state:
                raise AdvanceError("project state changed after dispatch planning")
            expected_tx = _expected_transaction(
                root=root,
                state_hash=current_state,
                next_id=next_id,
                action=action,
            )
            if expected_tx != action.get("transaction_id"):
                raise AdvanceError("transaction id is not bound to the current action and state")
            if expected_tx in seen_transactions:
                stop_reason = "cycle_detected"
                break
            seen_transactions.add(expected_tx)

            existing = load_receipt(root, expected_tx)
            if isinstance(existing, dict):
                if existing.get("state") == "completed":
                    stop_reason = "duplicate_transaction"
                    break
                raise AdvanceError("prior transaction is incomplete; reconciliation required")
            input_hash = stable_hash(
                {
                    "root": str(root),
                    "state_hash": current_state,
                    "next_id": next_id,
                    "skill_id": action.get("skill_id"),
                    "argv": argv,
                    "input_hashes": action.get("input_hashes") or {},
                }
            )
            receipt = begin_receipt(
                root,
                transaction=expected_tx,
                skill_id=str(action.get("skill_id") or ""),
                input_hash=input_hash,
                approval_class="none",
            )
            result = _sanitize_result(run(argv))
            if not result.get("ok"):
                complete_receipt(root, receipt, result)
                executed.append({"next_id": next_id, "transaction_id": expected_tx, **result})
                stop_reason = "action_failed"
                break
            verification = _verify_action(
                policy=policy,
                root=root,
                argv=argv,
                action_result=result,
                run=run,
            )
            combined = {
                "ok": bool(verification.get("ok")),
                "action": {
                    "returncode": result.get("returncode"),
                    "stdout": result.get("stdout"),
                    "stderr": result.get("stderr"),
                },
                "verification": verification,
            }
            complete_receipt(root, receipt, combined)
            executed.append(
                {
                    "next_id": next_id,
                    "transaction_id": expected_tx,
                    "ok": combined["ok"],
                    "verification_ok": bool(verification.get("ok")),
                }
            )
            if not verification.get("ok"):
                stop_reason = "verification_failed"
                break

        full_packet = build_dispatch(
            root,
            gates=gates,
            open_reshoot_count=open_reshoot_count,
            include_capability=False,
            write_receipt=True,
        )
        return {
            "ok": stop_reason not in {"action_failed", "verification_failed"},
            "kind": "ai-film-advance",
            "root": str(root),
            "executed": executed,
            "executed_count": len(executed),
            "stop_reason": stop_reason,
            "stop_detail": stop_detail,
            "next": compact_dispatch(full_packet),
        }
    except TransactionConflict as exc:
        raise AdvanceError(str(exc)) from exc
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
