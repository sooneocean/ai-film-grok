"""Dailies/selects/reshoot registry with budget-visible candidate accounting."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from util import read_json, write_json

STATUSES = {"select", "alternate", "reject", "reshoot"}


def _sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def update_dailies(
    root: Path | str,
    *,
    shot_id: str,
    candidate: str,
    status: str,
    reviewer: str,
    notes: str,
    approved_budget: int | None = None,
    provider: str = "",
    model: str = "",
    cost_usd: float | None = None,
    source_keyframe: str = "",
    qa: dict[str, Any] | None = None,
    director_score: int | None = None,
    issue_tags: list[str] | None = None,
    reshoot_decision: str = "",
    selection_rationale: str = "",
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError("status must be select|alternate|reject|reshoot")
    if not shot_id.strip() or not candidate.strip() or not reviewer.strip():
        raise ValueError("shot_id, candidate and reviewer are required")
    if cost_usd is not None and cost_usd < 0:
        raise ValueError("cost_usd must be >= 0")
    if director_score is not None and not 1 <= director_score <= 5:
        raise ValueError("director_score must be from 1 to 5")
    if reshoot_decision and reshoot_decision not in {"none", "reshoot", "repair"}:
        raise ValueError("reshoot_decision must be none|reshoot|repair")
    if status == "reshoot" and reshoot_decision not in {"", "reshoot"}:
        raise ValueError("reshoot status requires reshoot_decision=reshoot")
    if status != "reshoot" and reshoot_decision == "reshoot":
        raise ValueError("reshoot_decision=reshoot requires status=reshoot")
    base = Path(root).expanduser().resolve()
    path = base / "receipts" / "dailies.json"
    report = read_json(path) or {"schema_version": 1, "kind": "dailies", "shots": {}}
    shots = report.setdefault("shots", {})
    entries = shots.setdefault(shot_id, [])
    if approved_budget is not None:
        current = len(entries)
        if current >= int(approved_budget):
            raise ValueError(
                "approved candidate budget exhausted; request an explicit budget change"
            )
    media = Path(candidate).expanduser()
    if not media.is_absolute():
        media = base / media
    entry = {
        "candidate": str(media),
        "media_sha256": _sha(media),
        "status": status,
        "reviewer": reviewer.strip(),
        "notes": notes.strip(),
        "generation": {
            "provider": provider.strip() or None,
            "model": model.strip() or None,
            "cost_usd": cost_usd,
            "source_keyframe": source_keyframe.strip() or None,
        },
        "objective_qa": qa or {},
        "director_score": director_score,
        "issue_tags": sorted({item.strip() for item in (issue_tags or []) if item.strip()}),
        "reshoot_decision": reshoot_decision or ("reshoot" if status == "reshoot" else "none"),
        "selection_rationale": selection_rationale.strip(),
    }
    entries.append(entry)
    report["shot_count"] = len(shots)
    report["candidate_count"] = sum(len(items) for items in shots.values())
    report["budget_visible"] = approved_budget is not None
    report["ok"] = all(
        any(item.get("status") == "select" for item in items) for items in shots.values()
    )
    write_json(path, report)
    return report


def dailies_status(root: Path | str) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    report = read_json(base / "receipts" / "dailies.json") or {}
    stale: list[str] = []
    for shot_id, items in (report.get("shots") or {}).items():
        for item in items if isinstance(items, list) else []:
            candidate = Path(str(item.get("candidate") or ""))
            if not candidate.is_absolute():
                candidate = base / candidate
            if not candidate.is_file() or item.get("media_sha256") != _sha(candidate):
                stale.append(f"{shot_id}:{candidate.name}")
    return {
        **report,
        "stale_candidates": stale,
        "ok": bool(report) and not stale and bool(report.get("ok")),
    }
