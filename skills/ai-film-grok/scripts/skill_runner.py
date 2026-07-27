#!/usr/bin/env python3
"""Registry-bound skill runner with fixed argv mappings and resumable receipts."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from approval_ledger import approval_is_current, read_approval_ledger
from skill_registry import show_skill, validate_skill_payload
from transaction_receipt import (
    TransactionConflict,
    begin_receipt,
    complete_receipt,
    load_receipt,
    refuse_approved_output_overwrite,
    stable_hash,
    transaction_id,
)

Runner = Callable[[dict[str, Any], "RunnerSpec"], dict[str, Any]]
_SECRET_KEY = re.compile(r"(authorization|token|api[_-]?key|secret|signature|signed[_-]?url)", re.I)
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/-]+")


def _redact(value: Any, *, key: str = "") -> Any:
    if _SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(item_key): _redact(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _BEARER.sub("Bearer [REDACTED]", value)
    return value


@dataclass(frozen=True)
class RunnerSpec:
    operation: str
    argv: tuple[str, ...]
    spend_class: str
    approval_class: str
    runner: Runner | None = None


def _dispatch(payload: dict[str, Any], _spec: RunnerSpec) -> dict[str, Any]:
    from dispatch import build_dispatch

    return build_dispatch(
        Path(payload["projectRoot"]),
        include_capability=False,
        write_receipt=not bool(payload.get("dryRun")),
    )


def _director_argv(payload: dict[str, Any]) -> tuple[str, ...]:
    values = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    operation = str(values.get("operation") or "status")
    allowed = {"init", "migrate-audit", "migrate", "status", "check", "impact", "rebuild"}
    if operation not in allowed:
        raise ValueError(f"unsupported director operation: {operation}")
    argv = ["director", operation]
    if operation == "init":
        for field, flag in (
            ("title", "--title"),
            ("rigor", "--rigor"),
            ("formatPack", "--format-pack"),
            ("genrePack", "--genre-pack"),
        ):
            if values.get(field) is not None:
                argv.extend((flag, str(values[field])))
    elif operation == "migrate" and values.get("title") is not None:
        argv.extend(("--title", str(values["title"])))
    elif operation in {"impact", "rebuild"}:
        changed_refs = values.get("changedRefs")
        if not isinstance(changed_refs, list) or not changed_refs:
            raise ValueError(f"director {operation} requires changedRefs")
        for ref in changed_refs:
            argv.extend(("--changed-ref", str(ref)))
        if not str(values.get("reason") or "").strip():
            raise ValueError(f"director {operation} requires reason")
        argv.extend(("--reason", str(values["reason"])))
        if operation == "rebuild":
            if not isinstance(values.get("expectedRevision"), int):
                raise ValueError("director rebuild requires expectedRevision")
            argv.extend(("--expected-revision", str(values["expectedRevision"])))
            if values.get("transactionId"):
                argv.extend(("--transaction-id", str(values["transactionId"])))
    return tuple(argv)


def _department_argv(payload: dict[str, Any]) -> tuple[str, ...]:
    values = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    operation = str(values.get("operation") or "list")
    allowed = {"list", "show", "edit", "diff", "validate", "lock", "unlock", "status"}
    if operation not in allowed:
        raise ValueError(f"unsupported department operation: {operation}")
    argv = ["department", operation]
    if operation != "list":
        department_id = str(values.get("departmentId") or "")
        if not department_id:
            raise ValueError(f"department {operation} requires departmentId")
        argv.extend(("--id", department_id))
    if operation in {"edit", "diff"}:
        if not values.get("payloadFile"):
            raise ValueError(f"department {operation} requires payloadFile")
        argv.extend(("--payload-file", str(values["payloadFile"])))
    if operation in {"edit", "lock", "unlock"}:
        if not isinstance(values.get("expectedRevision"), int):
            raise ValueError(f"department {operation} requires expectedRevision")
        argv.extend(("--expected-revision", str(values["expectedRevision"])))
    if operation == "lock":
        if not values.get("approvalRef"):
            raise ValueError("department lock requires approvalRef")
        argv.extend(("--approval-ref", str(values["approvalRef"])))
    if operation == "unlock":
        if not str(values.get("reason") or "").strip():
            raise ValueError("department unlock requires reason")
        argv.extend(("--reason", str(values["reason"])))
    return tuple(argv)


def _director_control(payload: dict[str, Any], spec: RunnerSpec) -> dict[str, Any]:
    dynamic = RunnerSpec(
        spec.operation, _director_argv(payload), spec.spend_class, spec.approval_class
    )
    return _execute_subprocess(payload, dynamic, skill_id="director.control")


def _department_manage(payload: dict[str, Any], spec: RunnerSpec) -> dict[str, Any]:
    dynamic = RunnerSpec(
        spec.operation, _department_argv(payload), spec.spend_class, spec.approval_class
    )
    return _execute_subprocess(payload, dynamic, skill_id="department.manage")


def _media_queue_argv(payload: dict[str, Any], *, skill_id: str) -> tuple[str, ...]:
    """Compile a typed Registry request into the standalone media queue CLI."""
    values = payload.get("input") if isinstance(payload.get("input"), dict) else {}
    root = Path(payload["projectRoot"]).expanduser().resolve()
    node_ref = str(payload.get("nodeRef") or "")
    shot_id = node_ref.removeprefix("shot:")
    if not shot_id or shot_id == "project":
        raise ValueError(f"{skill_id} requires a shot nodeRef")

    allowed_operations = {
        "keyframe.generate": {"image_gen", "image_edit"},
        "image.animate": {"image_to_video", "reference_to_video"},
    }
    defaults = {
        "keyframe.generate": "image_gen",
        "image.animate": "image_to_video",
    }
    style = {}
    try:
        style = json.loads((root / "style-bible.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        style = {}
    style_reference = (
        style.get("style_reference") if isinstance(style.get("style_reference"), dict) else {}
    )
    default_operation = defaults[skill_id]
    # When the caller has not pinned an endpoint, a reference-first film uses
    # the multi-reference endpoint by default so the uploaded style image is
    # sent alongside the keyframe rather than being reduced to text guidance.
    if skill_id == "image.animate" and style_reference:
        default_operation = "reference_to_video"
    operation = str(values.get("operation") or default_operation)
    if operation not in allowed_operations[skill_id]:
        allowed = ", ".join(sorted(allowed_operations[skill_id]))
        raise ValueError(f"{skill_id} operation must be one of: {allowed}")

    prompt_value = values.get("promptFile")
    if not isinstance(prompt_value, str) or not prompt_value.strip():
        raise ValueError(f"{skill_id} requires input.promptFile")
    prompt = Path(prompt_value).expanduser()
    prompt = prompt.resolve() if prompt.is_absolute() else (root / prompt).resolve()

    raw_inputs = values.get("inputs") or []
    if isinstance(raw_inputs, str):
        raw_inputs = [raw_inputs]
    if not isinstance(raw_inputs, list) or not all(
        isinstance(item, str) and item.strip() for item in raw_inputs
    ):
        raise ValueError(f"{skill_id} input.inputs must be a list of paths")
    if style_reference:
        staged = Path(str(style_reference.get("staged_path") or "")).expanduser().resolve()
        if not staged.is_file():
            raise ValueError(f"{skill_id} uploaded style reference is missing: {staged}")
        resolved_inputs = {
            (
                Path(item).expanduser().resolve()
                if Path(item).expanduser().is_absolute()
                else (root / item).resolve()
            )
            for item in raw_inputs
        }
        if staged not in resolved_inputs:
            raw_inputs.append(str(staged))

    max_attempts = values.get("maxAttempts", 3)
    if (
        not isinstance(max_attempts, int)
        or isinstance(max_attempts, bool)
        or not 1 <= max_attempts <= 10
    ):
        raise ValueError(f"{skill_id} input.maxAttempts must be between 1 and 10")

    launcher = Path(__file__).with_name("media-queue")
    argv = [
        str(launcher),
        "add",
        "--root",
        str(root),
        "--shot-id",
        shot_id,
        "--operation",
        operation,
        "--prompt-file",
        str(prompt),
        "--max-attempts",
        str(max_attempts),
    ]
    for raw_input in raw_inputs:
        media_input = Path(raw_input).expanduser()
        media_input = (
            media_input.resolve() if media_input.is_absolute() else (root / media_input).resolve()
        )
        argv.extend(("--input", str(media_input)))
    assembly_receipt = values.get("assemblyReceipt")
    if assembly_receipt is None and style_reference:
        assembly_receipt = str(root / "receipts" / f"prompt_assembly_{shot_id}.json")
    if assembly_receipt is not None:
        if not isinstance(assembly_receipt, str) or not assembly_receipt.strip():
            raise ValueError(f"{skill_id} input.assemblyReceipt must be a path")
        receipt_path = Path(assembly_receipt).expanduser()
        receipt_path = (
            receipt_path.resolve()
            if receipt_path.is_absolute()
            else (root / receipt_path).resolve()
        )
        argv.extend(("--assembly-receipt", str(receipt_path)))
    return tuple(argv)


def _media_queue_run(payload: dict[str, Any], spec: RunnerSpec) -> dict[str, Any]:
    skill_id = str(payload["skillId"])
    return _execute_program(
        _media_queue_argv(payload, skill_id=skill_id),
        skill_id=skill_id,
    )


def _spec(
    operation: str,
    *argv: str,
    spend: str = "local",
    approval: str = "none",
    runner: Runner | None = None,
) -> RunnerSpec:
    return RunnerSpec(operation, tuple(argv), spend, approval, runner)


RUNNERS: dict[str, RunnerSpec] = {
    "director.control": _spec("director.control", runner=_director_control),
    "department.manage": _spec("department.manage", runner=_department_manage),
    "story.normalize": _spec("plan.normalize", "plan", "normalize"),
    "episode.structure": _spec("plan.run", "plan", "run"),
    "scene.segment": _spec("plan.run", "plan", "run"),
    "beat.extract": _spec("plan.run", "plan", "run"),
    "character.bible.build": _spec("bible.init", "bible", "init"),
    "character.state.update": _spec("assets.sync", "assets", "sync"),
    "location.bible.build": _spec("assets.sync", "assets", "sync"),
    "prop.track": _spec("assets.sync", "assets", "sync"),
    "heat.lint": _spec("heat.check", "heat", "check"),
    "heat.vo-suggest": _spec("heat.vo-suggest", "heat", "vo-suggest"),
    "shot.plan": _spec("plan.run", "plan", "run"),
    "panel.layout": _spec("graph.derive", "graph", "derive"),
    "keyframe.generate": _spec(
        "media-queue.add",
        spend="external",
        approval="human_required",
        runner=_media_queue_run,
    ),
    "continuity.check": _spec("lint-continuity", "lint-continuity"),
    "image.animate": _spec(
        "media-queue.add",
        spend="paid",
        approval="human_required",
        runner=_media_queue_run,
    ),
    "camera.motion.plan": _spec("motion-plan", "motion-plan"),
    "voice.synthesize": _spec(
        "tts-rehearse", "tts-rehearse", spend="external", approval="human_required"
    ),
    "subtitle.generate": _spec("final", "final"),
    "sound.design": _spec("audio-plan", "audio-plan"),
    "music.plan": _spec("audio-plan", "audio-plan"),
    "timeline.compose": _spec("assemble", "assemble"),
    "rhythm.evaluate": _spec("preflight", "preflight"),
    "video.render": _spec("final", "final", spend="external", approval="human_required"),
    "quality.inspect": _spec("review-final", "review-final", approval="human_required"),
    "export.package": _spec("export-desktop", "export-desktop", approval="human_required"),
    "dispatch.orchestrate": _spec("dispatch", "dispatch", runner=_dispatch),
    "story.validate": _spec("plan.validate", "plan", "validate", "--strict"),
    "beat.validate": _spec("plan.validate", "plan", "validate", "--strict"),
    "graph.project": _spec("graph.project", "graph", "project"),
    "projection.verify": _spec("plan.validate", "plan", "validate", "--strict"),
}


def _spend_scope(payload: dict[str, Any]) -> dict[str, Any]:
    scope = payload.get("spendScope")
    if not isinstance(scope, dict):
        raise ValueError("paid/external skill requires spendScope")
    shot_ids = scope.get("shotIds")
    candidate_count = scope.get("candidateCount")
    budget = scope.get("budget")
    valid = (
        isinstance(shot_ids, list)
        and bool(shot_ids)
        and len({str(item) for item in shot_ids}) == len(shot_ids)
        and all(isinstance(item, str) and item.strip() for item in shot_ids)
        and isinstance(candidate_count, int)
        and not isinstance(candidate_count, bool)
        and candidate_count > 0
        and isinstance(budget, dict)
        and isinstance(budget.get("maxUnits"), (int, float))
        and not isinstance(budget.get("maxUnits"), bool)
        and float(budget["maxUnits"]) > 0
        and isinstance(budget.get("currency"), str)
        and bool(budget["currency"].strip())
    )
    if not valid:
        raise ValueError(
            "spendScope requires unique shotIds, positive candidateCount, and budget maxUnits/currency"
        )
    return scope


def _require_current_approval(
    root: Path,
    *,
    skill_id: str,
    spec: RunnerSpec,
    payload: dict[str, Any],
    transaction: str,
) -> tuple[str, dict[str, str]]:
    approval_ref = payload.get("approvalRef")
    if isinstance(approval_ref, bool) or not isinstance(approval_ref, str) or not approval_ref:
        raise ValueError("current human approval ref is required")
    hashes = {"input": str(payload["inputHash"])}
    if spec.spend_class in {"paid", "bulk", "external"}:
        hashes["spend_scope"] = stable_hash(_spend_scope(payload))
    approval = next(
        (
            item
            for item in read_approval_ledger(root).get("approvals") or []
            if item.get("approval_id") == approval_ref
        ),
        None,
    )
    expected_scope = f"skill:{skill_id}:{payload['nodeRef']}"
    if (
        not isinstance(approval, dict)
        or approval.get("revoked") is True
        or approval.get("project_binding_current") is not True
        or approval.get("ledger_integrity_current") is not True
        or approval.get("approver_type") not in {"human", "user"}
        or approval.get("scope") != expected_scope
        or approval.get("approval_type") != "skill_run"
        or approval.get("transaction_id") != transaction
        or not approval_is_current(approval, hashes).get("ok")
    ):
        raise ValueError(
            "approval ref is not current for this skill, node, inputs, and spend scope"
        )
    return approval_ref, hashes


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid payload file: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    return payload


def _output_paths(root: Path, payload: dict[str, Any], result: dict[str, Any]) -> list[Path]:
    values: list[Any] = list(payload.get("expectedOutputs") or [])
    for asset in result.get("assets") or []:
        if isinstance(asset, dict) and asset.get("path"):
            values.append(asset["path"])
    paths: list[Path] = []
    for value in values:
        path = Path(str(value)).expanduser()
        paths.append(path if path.is_absolute() else root / path)
    return paths


def _execute_subprocess(
    payload: dict[str, Any], spec: RunnerSpec, *, skill_id: str
) -> dict[str, Any]:
    if not spec.argv:
        return {
            "ok": False,
            "skillId": skill_id,
            "error": "runner requires an external provider and cannot execute without approval adapter",
        }
    root = Path(payload["projectRoot"]).expanduser().resolve()
    launcher = Path(__file__).with_name("aifilm")
    argv = [str(launcher), *spec.argv, "--root", str(root)]
    return _execute_program(tuple(argv), skill_id=skill_id)


def _execute_program(argv: tuple[str, ...], *, skill_id: str) -> dict[str, Any]:
    process = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=3600)
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError:
        result = {
            "ok": process.returncode == 0,
            "stdout": process.stdout[-4000:],
            "stderr": process.stderr[-4000:],
        }
    result = _redact(result)
    if not isinstance(result, dict):
        result = {"ok": False, "error": "runner returned a non-object result"}
    result.setdefault("skillId", skill_id)
    return result


def run_skill(skill_id: str, payload_file: Path | str, *, dry_run: bool = False) -> dict[str, Any]:
    try:
        payload = _load_payload(Path(payload_file))
        shown = show_skill(skill_id)
        if not shown.get("ok"):
            return {"ok": False, "error": f"unknown skill: {skill_id}"}
        spec = RUNNERS.get(skill_id)
        if spec is None:
            return {"ok": False, "error": f"skill has no fixed runner mapping: {skill_id}"}
        payload.setdefault("skillId", skill_id)
        payload.setdefault("nodeRef", "project")
        payload.setdefault("inputHash", stable_hash(payload.get("input") or {}))
        validation = validate_skill_payload(skill_id, payload, direction="input")
        if not validation.get("ok") or not str(payload.get("projectRoot") or "").strip():
            errors = list(validation.get("errors") or [])
            if not payload.get("projectRoot"):
                errors.append("projectRoot is required")
            return {"ok": False, "error": "invalid skill payload", "errors": errors}
        root = Path(payload["projectRoot"]).expanduser().resolve()
        effective_dry_run = bool(dry_run or payload.get("dryRun"))
        tx = transaction_id(skill_id, payload)
        input_hash = stable_hash(payload)
        existing = load_receipt(root, tx)
        if existing is not None:
            if existing.get("input_hash") != input_hash or existing.get("skill_id") != skill_id:
                raise TransactionConflict("transaction id already belongs to different inputs")
            if existing.get("state") == "completed":
                result = dict(existing.get("result") or {})
                result.update({"transaction_id": tx, "resumed": True})
                return result
            if existing.get("state") in {"started", "failed"}:
                result = dict(existing.get("result") or {})
                result.update(
                    {
                        "ok": False,
                        "transaction_id": tx,
                        "resumed": True,
                        "reconciliation_required": True,
                        "error": "transaction is not safely repeatable; reconcile provider/output evidence",
                    }
                )
                return result
        planned_argv = spec.argv
        operation = spec.operation
        if skill_id == "director.control":
            planned_argv = _director_argv(payload)
            operation = f"director.{planned_argv[1]}"
        elif skill_id == "department.manage":
            planned_argv = _department_argv(payload)
            operation = f"department.{planned_argv[1]}"
        elif spec.runner is _media_queue_run:
            planned_argv = _media_queue_argv(payload, skill_id=skill_id)
            operation = "media-queue.add"
        report = {
            "ok": True,
            "skillId": skill_id,
            "nodeRef": payload["nodeRef"],
            "transaction_id": tx,
            "input_hash": input_hash,
            "dry_run": effective_dry_run,
            "runner": {
                "operation": operation,
                "argv": list(planned_argv),
                "spend_class": spec.spend_class,
                "approval_class": (
                    "human_required"
                    if spec.spend_class in {"paid", "bulk", "external"}
                    else spec.approval_class
                ),
            },
        }
        if effective_dry_run:
            return report
        approval_ref: str | None = None
        approval_input_hashes: dict[str, str] = {}
        if report["runner"]["approval_class"] == "human_required":
            approval_ref, approval_input_hashes = _require_current_approval(
                root, skill_id=skill_id, spec=spec, payload=payload, transaction=tx
            )
        refuse_approved_output_overwrite(root, payload)
        receipt = begin_receipt(
            root,
            transaction=tx,
            skill_id=skill_id,
            input_hash=input_hash,
            approval_class=str(report["runner"]["approval_class"]),
            approval_ref=approval_ref,
            approval_input_hashes=approval_input_hashes,
        )
        result = (
            spec.runner(payload, spec)
            if spec.runner is not None
            else _execute_subprocess(payload, spec, skill_id=skill_id)
        )
        result.setdefault("skillId", skill_id)
        result.setdefault("nodeRef", payload["nodeRef"])
        output_validation = validate_skill_payload(skill_id, result, direction="output")
        if not output_validation.get("ok"):
            result = {
                "ok": False,
                "skillId": skill_id,
                "nodeRef": payload["nodeRef"],
                "error": "runner output violated the skill result contract",
                "errors": output_validation.get("errors") or [],
            }
        result.update(
            {
                "transaction_id": tx,
                "input_hash": input_hash,
                "resumed": False,
            }
        )
        completed = complete_receipt(
            root, receipt, result, output_paths=_output_paths(root, payload, result)
        )
        return dict(completed["result"])
    except (TransactionConflict, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
