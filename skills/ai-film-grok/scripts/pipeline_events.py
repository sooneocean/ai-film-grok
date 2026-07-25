"""Append-only, non-secret execution events for optimisation metrics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from optimization_taxonomy import details
from util import canonical_json_sha256, exclusive_file_lock, utc_now

EVENTS_NAME = "pipeline-events.jsonl"
VALID_PHASES = frozenset({"started", "claimed", "registered", "completed", "failed", "human_time"})


def path_for(root: Path | str) -> Path:
    return Path(root).expanduser().resolve() / "receipts" / EVENTS_NAME


def append_event(
    root: Path | str,
    *,
    run_id: str = "default",
    stage: str,
    phase: str,
    shot_id: str | None = None,
    retry_of: str | None = None,
    error_code: str | None = None,
    human_minutes: float | None = None,
    actor: str | None = None,
    note: str | None = None,
    occurred_at: str | None = None,
) -> dict[str, Any]:
    if phase not in VALID_PHASES:
        raise ValueError(f"unsupported event phase: {phase}")
    if not str(stage).strip():
        raise ValueError("stage is required")
    if human_minutes is not None and human_minutes <= 0:
        raise ValueError("human_minutes must be > 0")
    raw = {
        "schema_version": 1,
        "run_id": str(run_id or "default"),
        "stage": str(stage),
        "phase": phase,
        "occurred_at": occurred_at or utc_now(),
        "shot_id": shot_id or None,
        "retry_of": retry_of or None,
        "human_minutes": human_minutes,
        "actor": actor or None,
        "note": note or None,
    }
    if error_code:
        raw["error"] = details(error_code)
    semantic = {key: value for key, value in raw.items() if value is not None}
    semantic["event_id"] = f"evt-{canonical_json_sha256(semantic)[:24]}"
    target = path_for(root)
    with exclusive_file_lock(target):
        target.parent.mkdir(parents=True, exist_ok=True)
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        if f'"event_id": "{semantic["event_id"]}"' not in existing:
            with target.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(semantic, ensure_ascii=False, sort_keys=True) + "\n")
    return semantic


def load_events(root: Path | str) -> tuple[list[dict[str, Any]], list[str]]:
    target = path_for(root)
    if not target.is_file():
        return [], []
    events: list[dict[str, Any]] = []
    invalid: list[str] = []
    for lineno, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            invalid.append(f"line:{lineno}")
            continue
        if not isinstance(item, dict) or not item.get("stage") or not item.get("phase"):
            invalid.append(f"line:{lineno}")
            continue
        events.append(item)
    return events, invalid
