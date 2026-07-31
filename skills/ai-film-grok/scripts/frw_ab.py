#!/usr/bin/env python3
"""FRW catalog-driven A/B control plane.

Pilot experiments fan out every eligible platform model unless an explicit
multi-model remediation subset is requested. Production experiments are limited
to a hash-bound, human-approved champion and challenger. This module never
changes ``i2v_provider`` and never treats machine ranking as approval.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from i2v_provider import provider_switch_receipt_is_valid
from security_policy import (
    SecurityPolicyError,
    safe_existing_file,
    safe_workspace_directory,
    validate_identifier,
)
from util import canonical_json_sha256, read_json, sha256_file, write_json

SCHEMA_VERSION = 1
SUPPORTED_OPERATIONS = frozenset(
    {
        "first_last_frame_to_video",
        "image_to_image",
        "image_to_video",
        "lip_sync",
        "motion_transfer",
        "text_to_image",
        "text_to_speech",
        "text_to_video",
        "video_enhancement",
    }
)
SUPPORTED_STAGES = frozenset({"pilot", "production"})
SUPPORTED_CONTENT_CLASSES = frozenset({"general", "restricted"})
REQUIRED_INPUTS = {
    "first_last_frame_to_video": frozenset({"prompt", "img1", "img2"}),
    "image_to_image": frozenset({"prompt", "img-url"}),
    "image_to_video": frozenset({"prompt", "img-url"}),
    "lip_sync": frozenset({"prompt", "img-url", "audio-url"}),
    "motion_transfer": frozenset({"prompt", "video-url"}),
    "text_to_image": frozenset({"prompt"}),
    "text_to_speech": frozenset({"prompt", "audio-url"}),
    "text_to_video": frozenset({"prompt"}),
    "video_enhancement": frozenset({"video-url"}),
}
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,159}$")
ERROR_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
PROVIDER_STATUSES = frozenset(
    {
        "cancelled",
        "completed",
        "failed",
        "pending",
        "processing",
        "queued",
        "running",
        "succeeded",
        "success",
    }
)
ASYNC_COMMANDS = {
    "first-last-frame": "flf-query",
    "img2image": "img2image-query",
    "img2video": "img2video-query",
    "newvideo": "newvideo-query",
    "text2image": "text2image-query",
    "text2video": "text2video-query",
    "tts": "tts-query",
}
IMAGE_OPERATIONS = frozenset({"image_to_image", "text_to_image"})
VIDEO_OPERATIONS = SUPPORTED_OPERATIONS - IMAGE_OPERATIONS - {"text_to_speech"}
INPUT_FLAGS = (
    "prompt",
    "img-url",
    "img1",
    "img2",
    "audio-url",
    "video-url",
    "aspect-ratio",
    "ratio",
    "resolution",
    "width",
    "height",
    "duration",
    "fps",
    "seed",
    "generate-audio",
    "title",
)
SELECTION_REJECT_MARKERS = (
    "draft",
    "proposal",
    "example",
    "template",
    "pending",
    "maybe",
    " if ",
    "草案",
    "初稿",
    "示例",
    "候选",
    "建议",
    "暂定",
    "待确认",
    "待確認",
    "如果",
    "若",
    "确认后",
    "確認後",
    "前提",
    "之后",
    "之後",
    "再批准",
    "再核准",
    "模型输出",
    "模型輸出",
    "引用",
    "假设",
    "假設",
)


class FrwABError(RuntimeError):
    """A stable A/B control-plane error."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _root(root: Path | str) -> Path:
    return Path(root).expanduser().resolve()


def _receipt_dir(root: Path | str) -> Path:
    base = _root(root)
    try:
        receipts = safe_workspace_directory(base, "receipts", field="receipts")
        receipts.mkdir(parents=True, exist_ok=True)
        directory = safe_workspace_directory(receipts, "frw-ab", field="FRW A/B receipts")
    except SecurityPolicyError as exc:
        raise FrwABError(f"INVALID_RECEIPT_PATH: {exc}") from exc
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _receipt_path(root: Path | str, experiment_id: str, kind: str) -> Path:
    try:
        stable_id = validate_identifier(experiment_id, field="experiment id")
    except SecurityPolicyError as exc:
        raise FrwABError(f"INVALID_EXPERIMENT_ID: {exc}") from exc
    return _receipt_dir(root) / f"{stable_id}-{kind}.json"


def _write_receipt(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    if path.is_symlink():
        raise FrwABError(f"INVALID_RECEIPT_PATH: symbolic-link receipt is not allowed: {path}")
    write_json(path, payload)
    path.chmod(0o600)
    return payload


def _value_hash(value: object) -> str:
    return canonical_json_sha256({"value": value})


def _receipt_hash(
    payload: dict[str, Any],
    *,
    hash_field: str,
    volatile_fields: frozenset[str],
) -> str:
    stable = {
        key: value
        for key, value in payload.items()
        if key != hash_field and key not in volatile_fields
    }
    return canonical_json_sha256(stable)


def _selection_role_pattern(model_id: str, role: str) -> re.Pattern[str]:
    escaped = re.escape(model_id.casefold())
    model = rf"(?<![a-z0-9_-]){escaped}(?![a-z0-9_-])"
    return re.compile(
        rf"(?:{model}\s*(?:为|為|as|is|=|:)\s*{role}\b|"
        rf"{role}\s*(?:为|為|as|is|=|:)\s*{model})",
        re.IGNORECASE,
    )


def selection_phrase_is_approval(phrase: str, *, champion: str, challenger: str) -> bool:
    """Require an explicit, role-bound user approval for FRW promotion."""
    value = str(phrase or "").strip()
    lowered = value.casefold()
    if (
        not value
        or any(marker in lowered for marker in SELECTION_REJECT_MARKERS)
        or re.search(r"\bif\b", lowered)
        or any(marker in value for marker in ("?", "？", "吗", "嗎", "么", "麼", "呢"))
    ):
        return False
    if not (value.startswith(("批准", "核准")) or re.match(r"^approve(?:d)?\b", lowered)):
        return False
    return bool(
        _selection_role_pattern(champion, "champion").search(lowered)
        and _selection_role_pattern(challenger, "challenger").search(lowered)
    )


def _selection_binding_hash(
    *, rank_sha256: str, user_phrase: str, champion: str, challenger: str
) -> str:
    return canonical_json_sha256(
        {
            "rank_sha256": rank_sha256,
            "user_phrase": user_phrase.strip(),
            "champion": champion,
            "challenger": challenger,
        }
    )


def _input_bindings(inputs: dict[str, str]) -> dict[str, dict[str, Any]]:
    return {
        key: {
            "sha256": _value_hash(value),
            "present": bool(str(value).strip()),
        }
        for key, value in sorted(inputs.items())
        if key in INPUT_FLAGS and str(value).strip()
    }


def _validate_inputs(operation: str, inputs: dict[str, str]) -> None:
    required = REQUIRED_INPUTS.get(operation)
    if required is None:
        raise FrwABError(f"INVALID_OPERATION: {operation}")
    missing = sorted(key for key in required if not str(inputs.get(key) or "").strip())
    if missing:
        raise FrwABError(f"INVALID_INPUTS: missing {','.join(missing)}")
    unknown = sorted(set(inputs) - set(INPUT_FLAGS))
    if unknown:
        raise FrwABError(f"INVALID_INPUTS: unsupported {','.join(unknown)}")
    if any(len(str(value)) > 16_384 or "\0" in str(value) for value in inputs.values()):
        raise FrwABError("INVALID_INPUTS: value is too large or contains NUL")


def _catalog_contract_hash(catalog: dict[str, Any]) -> str:
    stable = {
        key: catalog.get(key)
        for key in (
            "catalog_schema_version",
            "complete",
            "source",
            "usage_policy",
            "trust_domain",
            "allowed_content_classes",
            "capabilities",
        )
    }
    return canonical_json_sha256(stable)


def _validate_catalog(catalog: dict[str, Any]) -> None:
    if catalog.get("catalog_schema_version") != 1 or catalog.get("complete") is not True:
        raise FrwABError("CATALOG_INVALID: complete schema v1 catalog required")
    if catalog.get("trust_domain") != "company_internal":
        raise FrwABError("CATALOG_INVALID: FRW trust domain is not company_internal")
    usage = catalog.get("usage_policy")
    if not isinstance(usage, dict):
        raise FrwABError("CATALOG_INVALID: usage policy missing")
    if (
        usage.get("billing_class") != "internal_unmetered"
        or usage.get("fanout_allowed") is not True
        or usage.get("requires_cost_confirmation") is not False
    ):
        raise FrwABError("CATALOG_INVALID: unmetered fanout policy is not declared")
    if not isinstance(catalog.get("capabilities"), list):
        raise FrwABError("CATALOG_INVALID: capabilities must be an array")


def _eligible_candidates(
    catalog: dict[str, Any],
    *,
    operation: str,
    content_class: str,
) -> list[dict[str, Any]]:
    _validate_catalog(catalog)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for capability in catalog["capabilities"]:
        if not isinstance(capability, dict):
            raise FrwABError("CATALOG_INVALID: capability entry must be an object")
        invocation = capability.get("invocation")
        model = str(capability.get("model_id") or "").strip()
        command = str((invocation or {}).get("command") or "")
        if (
            capability.get("source") not in {"platform_catalog", "dispatcher_contract"}
            or capability.get("operation") != operation
            or capability.get("status") != "advertised"
            or not isinstance(invocation, dict)
            or invocation.get("callable") is not True
            or command not in ASYNC_COMMANDS
            or content_class not in set(capability.get("allowed_content_classes") or [])
        ):
            continue
        try:
            validate_identifier(model, field="FRW model id")
        except SecurityPolicyError as exc:
            raise FrwABError(f"CATALOG_INVALID: {exc}") from exc
        if model in seen:
            raise FrwABError(f"CATALOG_INVALID: duplicate model id {model}")
        seen.add(model)
        rows.append(
            {
                "capability_id": capability.get("capability_id"),
                "model_id": model,
                "operation": operation,
                "catalog_status": "advertised",
                "health_state": "pending_pilot_probe",
                "parameters": capability.get("parameters") or [],
                "invocation": {
                    "command": command,
                    "query_command": ASYNC_COMMANDS[command],
                    "fixed_args": invocation.get("fixed_args")
                    if isinstance(invocation.get("fixed_args"), dict)
                    else {},
                },
            }
        )
    rows.sort(key=lambda row: row["model_id"])
    if not rows:
        raise FrwABError(f"NO_ELIGIBLE_MODELS: operation={operation}")
    return rows


def _base_plan(
    root: Path | str,
    *,
    experiment_id: str,
    operation: str,
    stage: str,
    content_class: str,
    inputs: dict[str, str],
    catalog: dict[str, Any],
    candidates: list[dict[str, Any]],
    mode: str,
    promotion_sha256: str | None = None,
    shot_id: str | None = None,
) -> dict[str, Any]:
    if operation not in SUPPORTED_OPERATIONS:
        raise FrwABError(f"INVALID_OPERATION: {operation}")
    if stage not in SUPPORTED_STAGES:
        raise FrwABError(f"INVALID_STAGE: {stage}")
    if content_class not in SUPPORTED_CONTENT_CLASSES:
        raise FrwABError(f"INVALID_CONTENT_CLASS: {content_class}")
    _validate_inputs(operation, inputs)
    stable_id = validate_identifier(experiment_id, field="experiment id")
    plan = {
        "schema_version": SCHEMA_VERSION,
        "kind": "frw-ab-plan",
        "created_at": _now(),
        "experiment_id": stable_id,
        "stage": stage,
        "operation": operation,
        "content_class": content_class,
        "catalog_sha256": _catalog_contract_hash(catalog),
        "input_bindings": _input_bindings(inputs),
        "candidates": candidates,
        "promotion_sha256": promotion_sha256,
        "fanout": {
            "mode": mode,
            "parallel": True,
            "unmetered": True,
            "candidate_count": len(candidates),
            "declared_concurrency_limit": (
                (catalog.get("usage_policy") or {}).get("declared_concurrency_limit")
            ),
        },
        "provider_policy": {
            "primary_provider": "grok",
            "changes_primary_provider": False,
            "requires_provider_switch_receipt": (
                stage == "production" and operation == "image_to_video"
            ),
            "shot_id": shot_id,
            "automatic_quality_fallback": False,
        },
        "execution": {
            "authorized": False,
            "explicit_run_required": True,
            "automatic_resubmit": False,
        },
    }
    plan["plan_sha256"] = _receipt_hash(
        plan,
        hash_field="plan_sha256",
        volatile_fields=frozenset({"created_at"}),
    )
    _write_receipt(_receipt_path(root, stable_id, "plan"), plan)
    return plan


def build_plan(
    root: Path | str,
    *,
    experiment_id: str,
    operation: str,
    stage: str,
    content_class: str,
    inputs: dict[str, str],
    catalog: dict[str, Any],
    selected_models: list[str] | None = None,
) -> dict[str, Any]:
    """Build a pilot plan. Production must use a human promotion receipt."""
    if stage == "production":
        raise FrwABError("PROMOTION_REQUIRED: use a human-approved champion and challenger")
    candidates = _eligible_candidates(
        catalog,
        operation=operation,
        content_class=content_class,
    )
    mode = "all_eligible"
    if selected_models is not None:
        requested = [str(model).strip() for model in selected_models]
        eligible_by_model = {row["model_id"]: row for row in candidates}
        if (
            len(requested) < 2
            or len(set(requested)) != len(requested)
            or any(model not in eligible_by_model for model in requested)
        ):
            raise FrwABError("INVALID_MODEL_SELECTION: choose at least two unique eligible models")
        candidates = [eligible_by_model[model] for model in sorted(requested)]
        mode = "selected_eligible"
    return _base_plan(
        root,
        experiment_id=experiment_id,
        operation=operation,
        stage="pilot",
        content_class=content_class,
        inputs=inputs,
        catalog=catalog,
        candidates=candidates,
        mode=mode,
    )


def build_production_plan(
    root: Path | str,
    *,
    experiment_id: str,
    operation: str,
    content_class: str,
    inputs: dict[str, str],
    catalog: dict[str, Any],
    promotion: dict[str, Any],
    shot_id: str | None = None,
    allow_test_catalog_hash: bool = False,
) -> dict[str, Any]:
    eligible = _eligible_candidates(
        catalog,
        operation=operation,
        content_class=content_class,
    )
    if (
        not isinstance(promotion, dict)
        or promotion.get("kind") != "frw-ab-promotion"
        or promotion.get("approved") is not True
        or promotion.get("approved_by") != "user"
        or promotion.get("operation") != operation
    ):
        raise FrwABError("PROMOTION_REQUIRED: current human FRW A/B promotion missing")
    champion = str(promotion.get("champion") or "")
    challenger = str(promotion.get("challenger") or "")
    if not allow_test_catalog_hash:
        promotion_hash = str(promotion.get("promotion_sha256") or "")
        expected_promotion_hash = _receipt_hash(
            promotion,
            hash_field="promotion_sha256",
            volatile_fields=frozenset({"approved_at"}),
        )
        if not promotion_hash or promotion_hash != expected_promotion_hash:
            raise FrwABError("PROMOTION_TAMPERED: approval receipt hash mismatch")
        rank_sha = str(promotion.get("rank_sha256") or "")
        user_phrase = str(promotion.get("user_phrase") or "")
        expected_selection_binding = _selection_binding_hash(
            rank_sha256=rank_sha,
            user_phrase=user_phrase,
            champion=champion,
            challenger=challenger,
        )
        if (
            not selection_phrase_is_approval(
                user_phrase,
                champion=champion,
                challenger=challenger,
            )
            or promotion.get("selection_binding_sha256") != expected_selection_binding
        ):
            raise FrwABError("PROMOTION_TAMPERED: selection binding mismatch")
    catalog_hash = _catalog_contract_hash(catalog)
    if not allow_test_catalog_hash and promotion.get("catalog_sha256") != catalog_hash:
        raise FrwABError("PROMOTION_STALE: catalog contract changed")
    by_model = {row["model_id"]: row for row in eligible}
    if champion == challenger or champion not in by_model or challenger not in by_model:
        raise FrwABError("PROMOTION_STALE: champion or challenger is not eligible")
    stable_shot_id = None
    if operation == "image_to_video":
        if not shot_id:
            raise FrwABError("PROVIDER_SWITCH_REQUIRED: production I2V needs --shot-id")
        try:
            stable_shot_id = validate_identifier(shot_id, field="shot id")
        except SecurityPolicyError as exc:
            raise FrwABError(f"INVALID_SHOT_ID: {exc}") from exc
    return _base_plan(
        root,
        experiment_id=experiment_id,
        operation=operation,
        stage="production",
        content_class=content_class,
        inputs=inputs,
        catalog=catalog,
        candidates=[by_model[champion], by_model[challenger]],
        mode="champion_challenger",
        promotion_sha256=str(promotion.get("promotion_sha256") or "") or None,
        shot_id=stable_shot_id,
    )


def _verify_inputs(plan: dict[str, Any], inputs: dict[str, str]) -> None:
    expected = plan.get("input_bindings")
    actual = _input_bindings(inputs)
    if expected != actual:
        raise FrwABError("INPUT_BINDING_MISMATCH: inputs differ from the plan")


def _task_id(value: object) -> str:
    task_id = str(value or "").strip()
    if not TASK_ID_RE.fullmatch(task_id):
        raise FrwABError("SUBMIT_FAILED: provider returned an invalid task id")
    return task_id


def _submission_result(model: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if payload.get("success") is not True:
        return {
            "model_id": model,
            "status": "submit_failed",
            "error_code": _safe_error_code(data.get("error_code"), default="SUBMIT_FAILED"),
        }
    return {
        "model_id": model,
        "status": "submitted",
        "task_id": _task_id(data.get("task_id")),
    }


def _safe_error_code(value: object, *, default: str) -> str:
    code = str(value or "").strip()
    return code if ERROR_CODE_RE.fullmatch(code) else default


@contextmanager
def _exclusive_run(run_path: Path) -> Iterator[None]:
    lock_path = run_path.with_suffix(".lock")
    try:
        descriptor = os.open(
            lock_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise FrwABError("RUN_ALREADY_EXISTS: fanout submission is already in progress") from exc
    os.close(descriptor)
    try:
        yield
    finally:
        if run_path.is_file():
            lock_path.unlink(missing_ok=True)


def run_experiment(
    root: Path | str,
    *,
    plan: dict[str, Any],
    inputs: dict[str, str],
    submit: Callable[[dict[str, Any], dict[str, str]], dict[str, Any]],
) -> dict[str, Any]:
    experiment_id = str(plan.get("experiment_id") or "")
    expected_plan_hash = _receipt_hash(
        plan,
        hash_field="plan_sha256",
        volatile_fields=frozenset({"created_at"}),
    )
    if plan.get("plan_sha256") != expected_plan_hash:
        raise FrwABError("PLAN_TAMPERED: plan hash mismatch")
    _verify_provider_switch(root, plan)
    run_path = _receipt_path(root, experiment_id, "run")
    _verify_inputs(plan, inputs)
    candidates = plan.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise FrwABError("INVALID_PLAN: no candidates")
    with _exclusive_run(run_path):
        if run_path.exists():
            raise FrwABError("RUN_ALREADY_EXISTS: refusing duplicate fanout submission")
        return _submit_fanout(
            run_path,
            plan=plan,
            inputs=inputs,
            candidates=candidates,
            submit=submit,
        )


def _submit_fanout(
    run_path: Path,
    *,
    plan: dict[str, Any],
    inputs: dict[str, str],
    candidates: list[dict[str, Any]],
    submit: Callable[[dict[str, Any], dict[str, str]], dict[str, Any]],
) -> dict[str, Any]:
    submissions: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=len(candidates)) as pool:
        futures = {
            pool.submit(submit, dict(candidate), dict(inputs)): str(candidate["model_id"])
            for candidate in candidates
        }
        for future in as_completed(futures):
            model = futures[future]
            try:
                payload = future.result()
                if not isinstance(payload, dict):
                    raise FrwABError("provider response is not an object")
                result = _submission_result(model, payload)
            except Exception as exc:  # noqa: BLE001 - normalized before receipt
                result = {
                    "model_id": model,
                    "status": "submit_failed",
                    "error_code": (
                        str(exc).split(":", 1)[0]
                        if isinstance(exc, FrwABError)
                        else "SUBMIT_FAILED"
                    ),
                }
            submissions.append(result)
    submissions.sort(key=lambda row: row["model_id"])
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": "frw-ab-run",
        "created_at": _now(),
        "experiment_id": plan.get("experiment_id"),
        "stage": plan.get("stage"),
        "operation": plan.get("operation"),
        "plan_sha256": plan.get("plan_sha256"),
        "catalog_sha256": plan.get("catalog_sha256"),
        "fanout_count": len(submissions),
        "submissions": [
            {
                **row,
                "query_command": next(
                    (
                        str(candidate["invocation"]["query_command"])
                        for candidate in candidates
                        if candidate["model_id"] == row["model_id"]
                    ),
                    "newvideo-query",
                ),
            }
            for row in submissions
        ],
        "ok": all(row["status"] == "submitted" for row in submissions),
        "automatic_resubmit": False,
    }
    receipt["run_sha256"] = _receipt_hash(
        receipt,
        hash_field="run_sha256",
        volatile_fields=frozenset({"created_at"}),
    )
    return _write_receipt(run_path, receipt)


def _verify_run_receipt(run: dict[str, Any]) -> None:
    expected = _receipt_hash(
        run,
        hash_field="run_sha256",
        volatile_fields=frozenset({"created_at"}),
    )
    if run.get("run_sha256") != expected:
        raise FrwABError("RUN_TAMPERED: run receipt hash mismatch")


def poll_experiment(
    root: Path | str,
    *,
    run: dict[str, Any],
    query: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    _verify_run_receipt(run)
    submissions = [
        row
        for row in run.get("submissions") or []
        if isinstance(row, dict) and row.get("status") == "submitted"
    ]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, len(submissions))) as pool:
        futures = {pool.submit(query, dict(row)): row for row in submissions}
        for future in as_completed(futures):
            submission = futures[future]
            model = str(submission.get("model_id") or "")
            task_id = str(submission.get("task_id") or "")
            try:
                payload = future.result()
                data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                raw_status = str(data.get("status") or "").strip().lower()
                status = raw_status if raw_status in PROVIDER_STATUSES else "unknown"
                output_url = next(
                    (
                        str(data[key])
                        for key in (
                            "url",
                            "video_url",
                            "image_url",
                            "audio_url",
                            "output_url",
                        )
                        if data.get(key)
                    ),
                    "",
                )
                declared_url_sha256 = str(data.get("url_sha256") or "")
                result = {
                    "model_id": model,
                    "task_id": task_id,
                    "status": status,
                    "url_sha256": (
                        declared_url_sha256.lower()
                        if SHA256_RE.fullmatch(declared_url_sha256)
                        else (_value_hash(output_url) if output_url else None)
                    ),
                    "error_code": (
                        _safe_error_code(data.get("error_code"), default="PROVIDER_ERROR")
                        if data.get("error_code")
                        else None
                    ),
                }
            except Exception:  # noqa: BLE001 - provider details never enter receipt
                result = {
                    "model_id": model,
                    "task_id": task_id,
                    "status": "query_failed",
                    "error_code": "RUNTIME_ERROR",
                }
            results.append(result)
    results.sort(key=lambda row: row["model_id"])
    terminal_statuses = {
        "cancelled",
        "completed",
        "failed",
        "query_failed",
        "succeeded",
        "success",
    }
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": "frw-ab-poll",
        "created_at": _now(),
        "experiment_id": run.get("experiment_id"),
        "operation": run.get("operation"),
        "run_sha256": run.get("run_sha256"),
        "results": results,
        "terminal": bool(results) and all(row["status"] in terminal_statuses for row in results),
        "automatic_resubmit": False,
    }
    receipt["poll_sha256"] = _receipt_hash(
        receipt,
        hash_field="poll_sha256",
        volatile_fields=frozenset({"created_at"}),
    )
    return _write_receipt(
        _receipt_path(root, str(run.get("experiment_id") or ""), "poll"),
        receipt,
    )


def _verify_poll_receipt(poll: dict[str, Any], run: dict[str, Any]) -> None:
    expected_hash = _receipt_hash(
        poll,
        hash_field="poll_sha256",
        volatile_fields=frozenset({"created_at"}),
    )
    if poll.get("poll_sha256") != expected_hash:
        raise FrwABError("POLL_TAMPERED: poll receipt hash mismatch")
    if (
        poll.get("kind") != "frw-ab-poll"
        or poll.get("run_sha256") != run.get("run_sha256")
        or poll.get("experiment_id") != run.get("experiment_id")
        or poll.get("operation") != run.get("operation")
    ):
        raise FrwABError("POLL_BINDING_MISMATCH: poll does not bind the current run")
    expected_tasks = {
        (str(row.get("model_id") or ""), str(row.get("task_id") or ""))
        for row in run.get("submissions") or []
        if isinstance(row, dict) and row.get("status", "submitted") == "submitted"
    }
    results = [row for row in poll.get("results") or [] if isinstance(row, dict)]
    actual_tasks = {
        (str(row.get("model_id") or ""), str(row.get("task_id") or "")) for row in results
    }
    completed_statuses = {"completed", "succeeded", "success"}
    if (
        poll.get("terminal") is not True
        or len(results) != len(actual_tasks)
        or actual_tasks != expected_tasks
        or any(row.get("status") not in completed_statuses for row in results)
    ):
        raise FrwABError("POLL_NOT_READY: every submitted candidate must complete")


def rank_candidates(
    root: Path | str,
    *,
    run: dict[str, Any],
    poll: dict[str, Any],
    candidate_paths: dict[str, Path | str],
    analyze: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    _verify_run_receipt(run)
    _verify_poll_receipt(poll, run)
    base = _root(root)
    allowed_models = {
        str(row.get("model_id") or "")
        for row in run.get("submissions") or []
        if isinstance(row, dict) and row.get("task_id")
    }
    if set(candidate_paths) != allowed_models:
        raise FrwABError("CANDIDATE_SET_MISMATCH: attach exactly one file per submitted model")
    operation = str(run.get("operation") or "")
    if operation not in IMAGE_OPERATIONS | VIDEO_OPERATIONS:
        raise FrwABError(
            "UNSUPPORTED_RANK_MEDIA: this operation needs a dedicated local QA adapter"
        )
    rows: list[dict[str, Any]] = []
    for model, raw_path in sorted(candidate_paths.items()):
        try:
            path = safe_existing_file(base, raw_path, field=f"{model} candidate")
        except SecurityPolicyError as exc:
            raise FrwABError(f"INVALID_CANDIDATE_PATH: {exc}") from exc
        if operation in IMAGE_OPERATIONS:
            qa = analyze(
                path,
                aspect_ratio="9:16",
                min_width=704,
                min_height=1280,
            )
        else:
            qa = analyze(
                path,
                require_audio=False,
                require_motion=True,
                min_width=704,
                min_height=1280,
                expected_fps=24.0,
            )
        if not isinstance(qa, dict):
            raise FrwABError("MEDIA_QA_INVALID: analyzer returned no contract")
        viable = qa.get("ok") is True and (
            operation in IMAGE_OPERATIONS
            or (qa.get("decode_ok") is True and qa.get("motion_ok") is True)
        )
        row = {
            "model_id": model,
            "media": {
                "path": str(path.relative_to(base)),
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            },
            "qa": {
                key: qa.get(key)
                for key in (
                    "ok",
                    "decode_ok",
                    "motion_ok",
                    "motion_score",
                    "motion_continuity",
                    "width",
                    "height",
                    "fps",
                    "duration_sec",
                    "aspect",
                    "codes",
                    "soft_codes",
                    "errors",
                )
            },
            "viable": viable,
        }
        row["machine_score"] = {
            "motion_score": float(qa.get("motion_score") or 0.0),
            "motion_continuity": float(qa.get("motion_continuity") or 0.0),
            "pixel_count": int(qa.get("width") or 0) * int(qa.get("height") or 0),
            "media_bytes": path.stat().st_size,
        }
        rows.append(row)
    viable_rows = [row for row in rows if row["viable"]]
    viable_rows.sort(key=lambda row: row["model_id"])
    viable_rows.sort(
        key=lambda row: (
            row["machine_score"]["motion_score"],
            row["machine_score"]["motion_continuity"],
            row["machine_score"]["pixel_count"],
            row["machine_score"]["media_bytes"],
        ),
        reverse=True,
    )
    if len(viable_rows) < 2:
        raise FrwABError("INSUFFICIENT_VIABLE_CANDIDATES: champion and challenger required")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": "frw-ab-rank",
        "created_at": _now(),
        "experiment_id": run.get("experiment_id"),
        "operation": run.get("operation"),
        "catalog_sha256": run.get("catalog_sha256"),
        "run_sha256": run.get("run_sha256"),
        "poll_sha256": poll.get("poll_sha256"),
        "ranking_policy": [
            "media_qa_hard_gate",
            "motion_score",
            "motion_continuity",
            "pixel_count",
            "media_bytes",
            "stable_model_id",
        ],
        "ranked": viable_rows,
        "rejected": [row for row in rows if not row["viable"]],
        "provisional": {
            "champion": viable_rows[0]["model_id"],
            "challenger": viable_rows[1]["model_id"],
        },
        "status": "pending_human_approval",
        "approved": False,
    }
    receipt["rank_sha256"] = _receipt_hash(
        receipt,
        hash_field="rank_sha256",
        volatile_fields=frozenset({"created_at"}),
    )
    return _write_receipt(
        _receipt_path(root, str(run.get("experiment_id") or ""), "rank"),
        receipt,
    )


def approve_rank(
    root: Path | str,
    *,
    rank: dict[str, Any],
    champion: str,
    challenger: str,
    user_phrase: str,
) -> dict[str, Any]:
    expected_rank_hash = _receipt_hash(
        rank,
        hash_field="rank_sha256",
        volatile_fields=frozenset({"created_at"}),
    )
    if not rank.get("rank_sha256") or rank.get("rank_sha256") != expected_rank_hash:
        raise FrwABError("RANK_TAMPERED: ranking receipt hash mismatch")
    ranked_models = [
        str(row.get("model_id") or "") for row in rank.get("ranked") or [] if isinstance(row, dict)
    ]
    if champion == challenger or champion not in ranked_models or challenger not in ranked_models:
        raise FrwABError("INVALID_PROMOTION: choose two distinct ranked candidates")
    if not selection_phrase_is_approval(
        user_phrase,
        champion=champion,
        challenger=challenger,
    ):
        raise FrwABError(
            "HUMAN_APPROVAL_REQUIRED: phrase must bind each selected model to its exact role"
        )
    rank_sha = str(rank["rank_sha256"])
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": "frw-ab-promotion",
        "approved": True,
        "approved_by": "user",
        "approved_at": _now(),
        "user_phrase": user_phrase.strip(),
        "experiment_id": rank.get("experiment_id"),
        "operation": rank.get("operation"),
        "catalog_sha256": rank.get("catalog_sha256"),
        "rank_sha256": rank_sha,
        "champion": champion,
        "challenger": challenger,
        "selection_binding_sha256": _selection_binding_hash(
            rank_sha256=rank_sha,
            user_phrase=user_phrase,
            champion=champion,
            challenger=challenger,
        ),
        "changes_primary_provider": False,
        "requires_provider_switch_receipt": rank.get("operation") == "image_to_video",
    }
    operation = str(rank.get("operation") or "")
    if operation not in SUPPORTED_OPERATIONS:
        raise FrwABError("INVALID_PROMOTION: rank operation is invalid")
    receipt["promotion_sha256"] = _receipt_hash(
        receipt,
        hash_field="promotion_sha256",
        volatile_fields=frozenset({"approved_at"}),
    )
    return _write_receipt(
        _receipt_dir(root) / f"promotion-{operation}.json",
        receipt,
    )


def _parse_envelope(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise FrwABError("FRW_PROTOCOL_INVALID: no JSON envelope")


def invoke_frw(argv: list[str], *, timeout: float = 180.0) -> dict[str, Any]:
    """Invoke only the public frwclaw dispatcher contract."""
    from frw_dispatch import load_dotenv, resolve_frw_root, resolve_python

    root = resolve_frw_root()
    dispatch = root / "img-video-frw" / "scripts" / "dispatch.py"
    env = __import__("os").environ.copy()
    load_dotenv(root, env)
    env["PYTHONPATH"] = ""
    proc = subprocess.run(
        [resolve_python(root), str(dispatch), *argv],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    payload = _parse_envelope(proc.stdout or "")
    if proc.returncode not in {0, 1, 2, 3}:
        raise FrwABError("FRW_PROTOCOL_INVALID: unsupported exit code")
    return payload


def fetch_catalog() -> dict[str, Any]:
    payload = invoke_frw(["capabilities"], timeout=60)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    if payload.get("success") is not True or not isinstance(data, dict):
        raise FrwABError("CATALOG_UNAVAILABLE: FRW capabilities failed")
    _validate_catalog(data)
    return data


def _frw_submit_candidate(candidate: dict[str, Any], inputs: dict[str, str]) -> dict[str, Any]:
    invocation = candidate.get("invocation")
    if not isinstance(invocation, dict):
        raise FrwABError("INVALID_PLAN: candidate invocation missing")
    command = str(invocation.get("command") or "")
    if command not in ASYNC_COMMANDS:
        raise FrwABError("INVALID_PLAN: unsupported candidate command")
    argv = [command]
    fixed_args = invocation.get("fixed_args")
    if isinstance(fixed_args, dict):
        for key, value in sorted(fixed_args.items()):
            if value not in {None, ""}:
                argv.extend((f"--{key}", str(value)))
    declared_parameters = {
        str(parameter.get("name") or "")
        for parameter in candidate.get("parameters") or []
        if isinstance(parameter, dict)
    }
    aliases = {
        "img-url": ("img-url", "image_url", "image", "imageUrls"),
        "img1": ("img1", "image_url", "image", "first_img_url"),
        "img2": ("img2", "image2_url", "last_img_url"),
        "audio-url": ("audio-url", "audio_url", "audioUrls"),
        "video-url": ("video-url", "video_url", "videoUrls"),
    }
    for key in INPUT_FLAGS:
        value = inputs.get(key)
        if value:
            output_key = (
                "positive-prompt" if command == "first-last-frame" and key == "prompt" else key
            )
            output_key = "text" if command == "tts" and key == "prompt" else output_key
            if command != "newvideo" and key in aliases:
                output_key = next(
                    (name for name in aliases[key] if name in declared_parameters), output_key
                )
            argv.extend((f"--{output_key}", str(value)))
    return invoke_frw(argv)


def _frw_query(submission: dict[str, Any]) -> dict[str, Any]:
    task_id = _task_id(submission.get("task_id"))
    query_command = str(submission.get("query_command") or "")
    if query_command not in set(ASYNC_COMMANDS.values()):
        raise FrwABError("INVALID_RUN: unsupported query command")
    return invoke_frw([query_command, "--task-id", task_id], timeout=60)


def _load_required(path: Path, *, kind: str) -> dict[str, Any]:
    if path.is_symlink():
        raise FrwABError(f"INVALID_RECEIPT_PATH: symbolic-link receipt is not allowed: {path}")
    payload = read_json(path)
    if not isinstance(payload, dict) or payload.get("kind") != kind:
        raise FrwABError(f"RECEIPT_MISSING: {path}")
    return payload


def _verify_provider_switch(root: Path | str, plan: dict[str, Any]) -> None:
    policy = plan.get("provider_policy")
    if not isinstance(policy, dict) or policy.get("requires_provider_switch_receipt") is not True:
        return
    shot_id = str(policy.get("shot_id") or "")
    try:
        stable_shot_id = validate_identifier(shot_id, field="shot id")
    except SecurityPolicyError as exc:
        raise FrwABError(f"PROVIDER_SWITCH_REQUIRED: {exc}") from exc
    base = _root(root)
    unresolved = base / "receipts" / f"provider-switch-{stable_shot_id}.json"
    if unresolved.is_symlink():
        raise FrwABError("INVALID_RECEIPT_PATH: provider-switch receipt is a symlink")
    try:
        path = safe_existing_file(base, unresolved, field="provider-switch receipt")
    except SecurityPolicyError as exc:
        raise FrwABError(f"PROVIDER_SWITCH_REQUIRED: {exc}") from exc
    receipt = _load_required(path, kind="provider-switch")
    if (
        receipt.get("shot_id") != stable_shot_id
        or receipt.get("primary_provider") != "grok"
        or receipt.get("fallback_provider") != "frw-img2video"
        or receipt.get("reason_class") != "technical_failure"
        or not str(receipt.get("error") or "").strip()
        or receipt.get("fallback_fixed_for_shot") is not True
        or receipt.get("plan_sha256") != plan.get("plan_sha256")
        or not provider_switch_receipt_is_valid(receipt)
    ):
        raise FrwABError("PROVIDER_SWITCH_REQUIRED: invalid technical-failure receipt")


def _cli_inputs(args: argparse.Namespace) -> dict[str, str]:
    values: dict[str, str] = {}
    prompt = str(getattr(args, "prompt", None) or "")
    prompt_file = getattr(args, "prompt_file", None)
    if prompt_file:
        path = safe_existing_file(_root(args.root), prompt_file, field="prompt file")
        prompt = path.read_text(encoding="utf-8")
    if prompt:
        values["prompt"] = prompt
    for key in INPUT_FLAGS:
        if key == "prompt":
            continue
        attr = key.replace("-", "_")
        value = getattr(args, attr, None)
        if value not in {None, ""}:
            values[key] = str(value)
    return values


def _emit(data: dict[str, Any], *, success: bool = True) -> None:
    print(
        json.dumps(
            {
                "protocol_version": "1.0",
                "success": success,
                "done": True,
                "next_action": "ok" if success else "error",
                "user_reply": (
                    f"FRW A/B {data.get('kind', 'operation')} {'完成' if success else '失败'}"
                ),
                "data": data,
            },
            ensure_ascii=False,
        )
    )


def _add_inputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--prompt")
    parser.add_argument("--prompt-file")
    for key in INPUT_FLAGS:
        if key == "prompt":
            continue
        parser.add_argument(f"--{key}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="frw ab")
    sub = parser.add_subparsers(dest="action", required=True)

    catalog = sub.add_parser("catalog", help="Read and optionally snapshot FRW catalog")
    catalog.add_argument("--root")

    plan = sub.add_parser("plan", help="Plan pilot all-model or approved production A/B")
    plan.add_argument("--root", required=True)
    plan.add_argument("--experiment-id", required=True)
    plan.add_argument("--operation", required=True, choices=sorted(SUPPORTED_OPERATIONS))
    plan.add_argument("--stage", choices=sorted(SUPPORTED_STAGES), default="pilot")
    plan.add_argument("--shot-id", help="Required for production image_to_video")
    plan.add_argument(
        "--content-class", choices=sorted(SUPPORTED_CONTENT_CLASSES), default="general"
    )
    plan.add_argument(
        "--model",
        action="append",
        help="Pilot-only eligible model subset; repeat at least twice",
    )
    _add_inputs(plan)

    run = sub.add_parser("run", help="Explicitly submit a planned fanout once")
    run.add_argument("--root", required=True)
    run.add_argument("--experiment-id", required=True)
    _add_inputs(run)

    poll = sub.add_parser("poll", help="Query every submitted task once")
    poll.add_argument("--root", required=True)
    poll.add_argument("--experiment-id", required=True)

    rank = sub.add_parser("rank", help="Run local media QA and provisional ranking")
    rank.add_argument("--root", required=True)
    rank.add_argument("--experiment-id", required=True)
    rank.add_argument(
        "--candidate",
        action="append",
        required=True,
        help="model_id=film-local-path; repeat once per submitted model",
    )

    approve = sub.add_parser("approve", help="Record exact human champion/challenger")
    approve.add_argument("--root", required=True)
    approve.add_argument("--experiment-id", required=True)
    approve.add_argument("--champion", required=True)
    approve.add_argument("--challenger", required=True)
    approve.add_argument("--user-phrase", required=True)

    status = sub.add_parser("status", help="Read current A/B receipts")
    status.add_argument("--root", required=True)
    status.add_argument("--experiment-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.action == "catalog":
            catalog = fetch_catalog()
            if args.root:
                payload = {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "frw-ab-catalog",
                    "captured_at": _now(),
                    "catalog_sha256": _catalog_contract_hash(catalog),
                    "catalog": catalog,
                }
                _write_receipt(_receipt_dir(args.root) / "catalog.json", payload)
                _emit(payload)
            else:
                _emit(catalog)
            return 0

        if args.action == "plan":
            catalog = fetch_catalog()
            inputs = _cli_inputs(args)
            if args.stage == "production":
                if args.model:
                    raise FrwABError(
                        "INVALID_MODEL_SELECTION: --model is only valid for pilot plans"
                    )
                promotion = _load_required(
                    _receipt_dir(args.root) / f"promotion-{args.operation}.json",
                    kind="frw-ab-promotion",
                )
                report = build_production_plan(
                    args.root,
                    experiment_id=args.experiment_id,
                    operation=args.operation,
                    content_class=args.content_class,
                    inputs=inputs,
                    catalog=catalog,
                    promotion=promotion,
                    shot_id=args.shot_id,
                )
            else:
                report = build_plan(
                    args.root,
                    experiment_id=args.experiment_id,
                    operation=args.operation,
                    stage="pilot",
                    content_class=args.content_class,
                    inputs=inputs,
                    catalog=catalog,
                    selected_models=args.model,
                )
            _emit(report)
            return 0

        if args.action == "run":
            plan = _load_required(
                _receipt_path(args.root, args.experiment_id, "plan"),
                kind="frw-ab-plan",
            )
            report = run_experiment(
                args.root,
                plan=plan,
                inputs=_cli_inputs(args),
                submit=_frw_submit_candidate,
            )
            _emit(report, success=bool(report.get("ok")))
            return 0 if report.get("ok") else 1

        if args.action == "poll":
            run = _load_required(
                _receipt_path(args.root, args.experiment_id, "run"),
                kind="frw-ab-run",
            )
            report = poll_experiment(args.root, run=run, query=_frw_query)
            _emit(report)
            return 0

        if args.action == "rank":
            run = _load_required(
                _receipt_path(args.root, args.experiment_id, "run"),
                kind="frw-ab-run",
            )
            poll = _load_required(
                _receipt_path(args.root, args.experiment_id, "poll"),
                kind="frw-ab-poll",
            )
            operation = str(run.get("operation") or "")
            if operation in IMAGE_OPERATIONS:
                from media_qa import analyze_still_geometry as analyze_candidate
            else:
                from media_qa import analyze_media as analyze_candidate
            candidates: dict[str, str] = {}
            for value in args.candidate:
                model, separator, path = value.partition("=")
                if not separator or not model or not path or model in candidates:
                    raise FrwABError("INVALID_CANDIDATE: expected unique model=path")
                candidates[model] = path
            report = rank_candidates(
                args.root,
                run=run,
                poll=poll,
                candidate_paths=candidates,
                analyze=analyze_candidate,
            )
            _emit(report)
            return 0

        if args.action == "approve":
            rank = _load_required(
                _receipt_path(args.root, args.experiment_id, "rank"),
                kind="frw-ab-rank",
            )
            report = approve_rank(
                args.root,
                rank=rank,
                champion=args.champion,
                challenger=args.challenger,
                user_phrase=args.user_phrase,
            )
            _emit(report)
            return 0

        base = _root(args.root)
        try:
            receipts = safe_workspace_directory(base, "receipts", field="receipts")
            directory = safe_workspace_directory(
                receipts,
                "frw-ab",
                field="FRW A/B receipts",
            )
        except SecurityPolicyError as exc:
            raise FrwABError(f"INVALID_RECEIPT_PATH: {exc}") from exc
        if args.experiment_id:
            prefix = validate_identifier(args.experiment_id, field="experiment id")
            paths = sorted(directory.glob(f"{prefix}-*.json"))
            paths = sorted({*paths, *directory.glob("promotion-*.json")})
        else:
            paths = sorted(directory.glob("*.json")) if directory.is_dir() else []
        report = {
            "schema_version": SCHEMA_VERSION,
            "kind": "frw-ab-status",
            "root": str(_root(args.root)),
            "receipts": [
                {
                    "name": path.name,
                    "sha256": sha256_file(path),
                    "kind": receipt.get("kind"),
                }
                for path in paths
                if path.is_file()
                and not path.is_symlink()
                and isinstance(receipt := read_json(path), dict)
                and not (
                    args.experiment_id
                    and receipt.get("kind") == "frw-ab-promotion"
                    and receipt.get("experiment_id") != prefix
                )
            ],
            "read_only": True,
        }
        _emit(report)
        return 0
    except (FrwABError, SecurityPolicyError, OSError, subprocess.SubprocessError) as exc:
        code = str(exc).split(":", 1)[0] or "FRW_AB_ERROR"
        _emit({"kind": "frw-ab-error", "error_code": code}, success=False)
        return 2 if code.startswith(("INVALID_", "PROMOTION_", "HUMAN_")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
