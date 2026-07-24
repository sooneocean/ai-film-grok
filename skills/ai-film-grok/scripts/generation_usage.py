#!/usr/bin/env python3
"""Exact-first accounting for media-generation provider requests."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from util import canonical_json_sha256, exclusive_file_lock, read_json, sha256_file, write_json

LEDGER_RELATIVE_PATH = Path("receipts/generation-usage.json")
OPERATIONS = frozenset({"t2i", "image_edit", "i2v", "t2v", "tts"})
MEASUREMENTS = frozenset({"provider_exact", "local_zero", "manual_exact", "unknown"})
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "moderated"})
PHASES = frozenset({"started", "accepted", "finished"})
TOKEN_FIELDS = ("input_tokens", "output_tokens", "total_tokens")
USAGE_FIELDS = frozenset(
    {
        *TOKEN_FIELDS,
        "cost_in_usd_ticks",
        "generated_images",
        "video_seconds",
    }
)
_SAFE_TEXT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")


class GenerationUsageError(ValueError):
    """A generation usage event is unsafe, inconsistent, or not idempotent."""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def ledger_path(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / LEDGER_RELATIVE_PATH


def _empty_ledger() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "kind": "generation-usage",
        "revision": 0,
        "events": [],
    }


def _safe_text(value: object, field: str, *, required: bool = False) -> str | None:
    text = str(value or "").strip()
    if not text:
        if required:
            raise GenerationUsageError(f"{field} is required")
        return None
    if not _SAFE_TEXT.fullmatch(text):
        raise GenerationUsageError(f"{field} contains unsafe characters")
    return text


def _nonnegative_number(value: object, field: str, *, integer: bool) -> int | float:
    if isinstance(value, bool):
        raise GenerationUsageError(f"{field} must be numeric")
    try:
        if integer:
            decimal = Decimal(str(value))
            if not decimal.is_finite() or decimal != decimal.to_integral_value():
                raise GenerationUsageError(f"{field} must be an integer")
            number: int | float = int(decimal)
        else:
            number = float(value)
    except GenerationUsageError:
        raise
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise GenerationUsageError(f"{field} must be numeric") from exc
    if number < 0:
        raise GenerationUsageError(f"{field} must be >= 0")
    return number


def normalize_usage(value: object) -> dict[str, int | float]:
    """Retain only non-sensitive provider usage counters."""
    if not isinstance(value, dict):
        return {}
    aliases = {
        "prompt_tokens": "input_tokens",
        "completion_tokens": "output_tokens",
    }
    normalized: dict[str, int | float] = {}
    for raw_key, raw_value in value.items():
        key = aliases.get(str(raw_key), str(raw_key))
        if key not in USAGE_FIELDS or raw_value is None:
            continue
        normalized[key] = _nonnegative_number(
            raw_value,
            key,
            integer=key != "video_seconds",
        )
    return normalized


def _read_for_write(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return _empty_ledger()
    ledger = read_json(path)
    if not isinstance(ledger, dict) or not isinstance(ledger.get("events"), list):
        raise GenerationUsageError(f"generation usage ledger is corrupt: {path}")
    return ledger


def _event_semantics(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in event.items()
        if key not in {"event_id", "recorded_at", "event_sha256"}
    }


def _append_event(root: Path | str, event: dict[str, Any]) -> dict[str, Any]:
    path = ledger_path(root)
    with exclusive_file_lock(path):
        ledger = _read_for_write(path)
        semantics = _event_semantics(event)
        event_id = f"evt-{canonical_json_sha256(semantics)[:24]}"
        event = {
            "event_id": event_id,
            "recorded_at": utc_now(),
            **semantics,
        }
        event["event_sha256"] = canonical_json_sha256(_event_semantics(event))
        for existing in ledger["events"]:
            if existing.get("event_id") == event_id:
                return dict(existing)
            if existing.get("generation_id") == event.get("generation_id") and existing.get(
                "phase"
            ) == event.get("phase"):
                if _event_semantics(existing) == semantics:
                    return dict(existing)
                raise GenerationUsageError(
                    f"conflicting {event.get('phase')} event for {event.get('generation_id')}"
                )
        prior_phases = {
            existing.get("phase")
            for existing in ledger["events"]
            if existing.get("generation_id") == event.get("generation_id")
        }
        if event.get("phase") in {"accepted", "finished"} and "started" not in prior_phases:
            raise GenerationUsageError(
                f"{event.get('phase')} requires started event for {event.get('generation_id')}"
            )
        if event.get("phase") == "accepted" and "finished" in prior_phases:
            raise GenerationUsageError(
                f"accepted cannot follow finished for {event.get('generation_id')}"
            )
        ledger["events"].append(event)
        ledger["revision"] = int(ledger.get("revision") or 0) + 1
        ledger["updated_at"] = event["recorded_at"]
        ledger["content_sha256"] = canonical_json_sha256(
            {key: value for key, value in ledger.items() if key != "content_sha256"}
        )
        write_json(path, ledger)
        return dict(event)


def start_generation(
    root: Path | str,
    *,
    operation: str,
    provider: str,
    model: str = "",
    shot_id: str = "",
    job_id: str = "",
    generation_id: str | None = None,
) -> str:
    if operation not in OPERATIONS:
        raise GenerationUsageError(f"operation must be one of {sorted(OPERATIONS)}")
    gid = _safe_text(generation_id, "generation_id") if generation_id else f"gen-{uuid.uuid4().hex}"
    assert gid is not None
    event = {
        "schema_version": 1,
        "phase": "started",
        "generation_id": gid,
        "operation": operation,
        "provider": _safe_text(provider, "provider", required=True),
        "model": _safe_text(model, "model"),
        "shot_id": _safe_text(shot_id, "shot_id"),
        "job_id": _safe_text(job_id, "job_id"),
    }
    _append_event(root, event)
    return gid


def accept_generation(
    root: Path | str,
    generation_id: str,
    *,
    provider_request_id: str,
    usage: object = None,
) -> dict[str, Any]:
    normalized = normalize_usage(usage)
    return _append_event(
        root,
        {
            "schema_version": 1,
            "phase": "accepted",
            "generation_id": _safe_text(generation_id, "generation_id", required=True),
            "provider_request_id": _safe_text(
                provider_request_id, "provider_request_id", required=True
            ),
            "measurement": ("provider_exact" if "cost_in_usd_ticks" in normalized else "unknown"),
            "usage": normalized,
        },
    )


def finish_generation(
    root: Path | str,
    generation_id: str,
    *,
    status: str,
    usage: object = None,
    measurement: str = "unknown",
    provider_request_id: str = "",
    output: Path | str | None = None,
) -> dict[str, Any]:
    if status not in TERMINAL_STATUSES:
        raise GenerationUsageError(f"status must be one of {sorted(TERMINAL_STATUSES)}")
    if measurement not in MEASUREMENTS:
        raise GenerationUsageError(f"measurement must be one of {sorted(MEASUREMENTS)}")
    normalized = normalize_usage(usage)
    if measurement == "provider_exact" and "cost_in_usd_ticks" not in normalized:
        measurement = "unknown"
    if measurement == "manual_exact" and not normalized:
        raise GenerationUsageError("manual_exact requires at least one usage value")
    if measurement == "local_zero":
        if normalized.get("cost_in_usd_ticks") not in {None, 0}:
            raise GenerationUsageError("local_zero cannot have a non-zero cost")
        normalized["cost_in_usd_ticks"] = 0
    output_path: str | None = None
    output_hash: str | None = None
    if output is not None:
        media = Path(output).expanduser().resolve()
        if media.is_file():
            output_path = str(media)
            output_hash = sha256_file(media)
    return _append_event(
        root,
        {
            "schema_version": 1,
            "phase": "finished",
            "generation_id": _safe_text(generation_id, "generation_id", required=True),
            "status": status,
            "provider_request_id": _safe_text(provider_request_id, "provider_request_id"),
            "measurement": measurement,
            "usage": normalized,
            "output": output_path,
            "output_sha256": output_hash,
        },
    )


def manual_record(
    root: Path | str,
    *,
    operation: str,
    provider: str,
    model: str = "",
    status: str,
    measurement: str = "unknown",
    provider_request_id: str = "",
    output: Path | str | None = None,
    idempotency_key: str = "",
    shot_id: str = "",
    job_id: str = "",
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
    cost_in_usd_ticks: int | None = None,
) -> dict[str, Any]:
    output_hash = None
    if output is not None:
        media = Path(output).expanduser().resolve()
        if not media.is_file():
            raise GenerationUsageError(f"output is missing: {media}")
        output_hash = sha256_file(media)
    identity = (
        _safe_text(provider_request_id, "provider_request_id")
        or output_hash
        or _safe_text(idempotency_key, "idempotency_key")
    )
    if not identity:
        raise GenerationUsageError(
            "manual record needs provider_request_id, output, or idempotency key"
        )
    semantic_identity = {
        "operation": operation,
        "provider": provider,
        "model": model,
        "identity": identity,
    }
    gid = f"manual-{canonical_json_sha256(semantic_identity)[:24]}"
    start_generation(
        root,
        operation=operation,
        provider=provider,
        model=model,
        shot_id=shot_id,
        job_id=job_id,
        generation_id=gid,
    )
    usage = {
        key: value
        for key, value in {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost_in_usd_ticks": cost_in_usd_ticks,
        }.items()
        if value is not None
    }
    finish_generation(
        root,
        gid,
        status=status,
        usage=usage,
        measurement=measurement,
        provider_request_id=provider_request_id,
        output=output,
    )
    return usage_list(root, generation_id=gid)["records"][0]


def _load_events(root: Path | str) -> tuple[list[dict[str, Any]], str | None]:
    path = ledger_path(root)
    if not path.is_file():
        return [], None
    ledger = read_json(path)
    if not isinstance(ledger, dict) or not isinstance(ledger.get("events"), list):
        return [], f"corrupt generation usage ledger: {path}"
    events = [event for event in ledger["events"] if isinstance(event, dict)]
    return events, None


def _records_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for event in events:
        gid = str(event.get("generation_id") or "")
        if not gid:
            continue
        record = records.setdefault(
            gid,
            {
                "generation_id": gid,
                "status": "incomplete",
                "measurement": "unknown",
                "usage": {},
            },
        )
        phase = event.get("phase")
        if phase == "started":
            for key in ("operation", "provider", "model", "shot_id", "job_id"):
                if event.get(key) is not None:
                    record[key] = event.get(key)
            record["started_at"] = event.get("recorded_at")
        elif phase == "accepted":
            record["provider_request_id"] = event.get("provider_request_id")
            accepted_usage = event.get("usage")
            if isinstance(accepted_usage, dict):
                record["usage"] = dict(accepted_usage)
            if event.get("measurement") is not None:
                record["measurement"] = event.get("measurement")
            record["accepted_at"] = event.get("recorded_at")
        elif phase == "finished":
            for key in ("status", "output", "output_sha256", "provider_request_id"):
                if event.get(key) is not None:
                    record[key] = event.get(key)
            finished_usage = event.get("usage")
            if isinstance(finished_usage, dict):
                merged_usage = {
                    **(record.get("usage") if isinstance(record.get("usage"), dict) else {}),
                    **finished_usage,
                }
                if (
                    "total_tokens" not in finished_usage
                    and "input_tokens" in merged_usage
                    and "output_tokens" in merged_usage
                ):
                    merged_usage["total_tokens"] = int(merged_usage["input_tokens"]) + int(
                        merged_usage["output_tokens"]
                    )
                record["usage"] = merged_usage
            finished_measurement = event.get("measurement")
            if finished_measurement != "unknown" or "cost_in_usd_ticks" not in record.get(
                "usage", {}
            ):
                record["measurement"] = finished_measurement
            record["finished_at"] = event.get("recorded_at")
    return sorted(
        records.values(),
        key=lambda item: str(item.get("started_at") or item.get("finished_at") or ""),
    )


def _usd_string(ticks: int) -> str:
    value = Decimal(ticks) / Decimal(10_000_000_000)
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    operations: Counter[str] = Counter()
    providers: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    measurements: Counter[str] = Counter()
    tokens = {"input": 0, "output": 0, "total": 0}
    token_reported = 0
    cost_ticks = 0
    unknown_cost = 0
    for record in records:
        operations[str(record.get("operation") or "unknown")] += 1
        providers[str(record.get("provider") or "unknown")] += 1
        statuses[str(record.get("status") or "incomplete")] += 1
        measurement = str(record.get("measurement") or "unknown")
        measurements[measurement] += 1
        usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
        if any(field in usage for field in TOKEN_FIELDS):
            token_reported += 1
            tokens["input"] += int(usage.get("input_tokens") or 0)
            tokens["output"] += int(usage.get("output_tokens") or 0)
            tokens["total"] += int(usage.get("total_tokens") or 0)
        if measurement in {"provider_exact", "manual_exact", "local_zero"} and (
            "cost_in_usd_ticks" in usage
        ):
            cost_ticks += int(usage["cost_in_usd_ticks"])
        else:
            unknown_cost += 1
    return {
        "requests_total": len(records),
        "operation_counts": dict(sorted(operations.items())),
        "provider_counts": dict(sorted(providers.items())),
        "status_counts": dict(sorted(statuses.items())),
        "measurement_counts": dict(sorted(measurements.items())),
        "tokens": tokens,
        "token_reported_requests": token_reported,
        "cost_in_usd_ticks": cost_ticks,
        "cost_usd": _usd_string(cost_ticks),
        "unknown_cost_requests": unknown_cost,
    }


def usage_status(root: Path | str) -> dict[str, Any]:
    events, warning = _load_events(root)
    records = _records_from_events(events)
    tracking = "tracking_not_started" if not events and warning is None else "active"
    report = {
        "ok": warning is None,
        "kind": "generation-usage-status",
        "root": str(Path(root).expanduser().resolve()),
        "tracking_status": tracking if warning is None else "corrupt",
        **summarize_records(records),
    }
    if warning:
        report["warnings"] = [warning]
    return report


def usage_list(
    root: Path | str,
    *,
    operation: str | None = None,
    generation_id: str | None = None,
) -> dict[str, Any]:
    events, warning = _load_events(root)
    records = _records_from_events(events)
    if operation:
        records = [record for record in records if record.get("operation") == operation]
    if generation_id:
        records = [record for record in records if record.get("generation_id") == generation_id]
    report = {
        "ok": warning is None,
        "kind": "generation-usage-list",
        "root": str(Path(root).expanduser().resolve()),
        "records": records,
        **summarize_records(records),
    }
    if warning:
        report["warnings"] = [warning]
    return report


def scan_usage(scan_root: Path | str) -> dict[str, Any]:
    base = Path(scan_root).expanduser().resolve()
    if not base.is_dir():
        raise GenerationUsageError(f"scan root is not a directory: {base}")
    records: list[dict[str, Any]] = []
    projects: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[Path] = set()
    for path in sorted(base.rglob(str(LEDGER_RELATIVE_PATH))):
        root = path.parent.parent.resolve()
        if root in seen:
            continue
        seen.add(root)
        events, warning = _load_events(root)
        if warning:
            warnings.append(warning)
            continue
        project_records = _records_from_events(events)
        records.extend(project_records)
        projects.append({"root": str(root), **summarize_records(project_records)})
    return {
        "ok": not warnings,
        "kind": "generation-usage-summary",
        "scan_root": str(base),
        "project_count": len(projects),
        "projects": projects,
        "warnings": warnings,
        **summarize_records(records),
    }


def format_usage_table(report: dict[str, Any]) -> str:
    records = report.get("records") if isinstance(report.get("records"), list) else []
    headers = ("operation", "provider", "status", "tokens", "cost_usd", "measurement", "shot")
    rows = [headers]
    for record in records:
        usage = record.get("usage") if isinstance(record.get("usage"), dict) else {}
        total_tokens = usage.get("total_tokens")
        ticks = usage.get("cost_in_usd_ticks")
        rows.append(
            (
                str(record.get("operation") or "-"),
                str(record.get("provider") or "-"),
                str(record.get("status") or "-"),
                str(total_tokens) if total_tokens is not None else "N/A",
                _usd_string(int(ticks)) if ticks is not None else "unknown",
                str(record.get("measurement") or "unknown"),
                str(record.get("shot_id") or "-"),
            )
        )
    widths = [max(len(row[index]) for row in rows) for index in range(len(headers))]
    return "\n".join(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row)) for row in rows
    )
