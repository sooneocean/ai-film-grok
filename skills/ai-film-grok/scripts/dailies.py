"""Dailies/selects/reshoot registry with budget-visible candidate accounting."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from film_spec import iter_film_spec_shots
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


def _current_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Project an append-only decision log to the latest decision per take path."""
    latest: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in items:
        key = str(item.get("candidate") or "")
        if key not in latest:
            order.append(key)
        latest[key] = item
    return [latest[key] for key in order]


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
    media = Path(candidate).expanduser()
    if not media.is_absolute():
        media = base / media
    media = media.resolve()
    if approved_budget is not None:
        current = len(_current_items(entries))
        media_key = str(media)
        existing_keys = {str(item.get("candidate") or "") for item in entries}
        if media_key not in existing_keys and current >= int(approved_budget):
            raise ValueError(
                "approved candidate budget exhausted; request an explicit budget change"
            )
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
    spec = read_json(base / "film-spec.json") or {}
    manifest = read_json(base / "manifest.json") or {}
    manifest_clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    planned = [
        str(shot.get("id") or shot.get("shot_id") or "").strip()
        for shot in iter_film_spec_shots(spec)
        if str(shot.get("id") or shot.get("shot_id") or "").strip()
    ]
    stale: list[str] = []
    issues: list[dict[str, str]] = []
    selections: list[dict[str, str]] = []
    shots = report.get("shots") if isinstance(report.get("shots"), dict) else {}
    for shot_id in planned:
        raw_items = shots.get(shot_id) if isinstance(shots.get(shot_id), list) else []
        items = _current_items(raw_items)
        if not items:
            issues.append({"shot_id": shot_id, "code": "DAILIES_SHOT_MISSING"})
            continue
        selects = [item for item in items if item.get("status") == "select"]
        if len(selects) != 1:
            issues.append({"shot_id": shot_id, "code": "DAILIES_SELECT_COUNT"})
        for item in items:
            status = str(item.get("status") or "")
            if status not in STATUSES:
                issues.append({"shot_id": shot_id, "code": "DAILIES_TAKE_UNCLASSIFIED"})
            if status == "reject" and not str(item.get("notes") or "").strip():
                issues.append({"shot_id": shot_id, "code": "DAILIES_REJECT_REASON_MISSING"})
        if len(selects) == 1:
            selected = selects[0]
            selected_hash = str(selected.get("media_sha256") or "")
            clip = (
                manifest_clips.get(shot_id) if isinstance(manifest_clips.get(shot_id), dict) else {}
            )
            clip_path = Path(str(clip.get("path") or ""))
            if clip_path and not clip_path.is_absolute():
                clip_path = base / clip_path
            manifest_hash = str(clip.get("sha256") or clip.get("media_sha256") or "")
            if not manifest_hash and clip_path.is_file():
                manifest_hash = str(_sha(clip_path) or "")
            if clip.get("status") != "approved" or not manifest_hash:
                issues.append({"shot_id": shot_id, "code": "MANIFEST_CLIP_NOT_APPROVED"})
            elif selected_hash != manifest_hash:
                issues.append({"shot_id": shot_id, "code": "SELECT_MANIFEST_HASH_MISMATCH"})
            selections.append(
                {
                    "shot_id": shot_id,
                    "candidate": str(selected.get("candidate") or ""),
                    "media_sha256": selected_hash,
                }
            )
    for shot_id, items in shots.items():
        for item in _current_items(items) if isinstance(items, list) else []:
            candidate = Path(str(item.get("candidate") or ""))
            if not candidate.is_absolute():
                candidate = base / candidate
            if not candidate.is_file() or item.get("media_sha256") != _sha(candidate):
                stale.append(f"{shot_id}:{candidate.name}")
    if stale:
        issues.extend(
            {"shot_id": value.split(":", 1)[0], "code": "DAILIES_MEDIA_STALE"} for value in stale
        )
    selected_set_sha256 = hashlib.sha256(
        json.dumps(selections, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    professional = (read_json(base / "production-book.json") or {}).get("rigor") == "professional"
    ok = (
        bool(planned) and not issues
        if planned or professional
        else bool(report) and not stale and bool(report.get("ok"))
    )
    return {
        **report,
        "planned_shot_ids": planned,
        "selections": selections,
        "selected_set_sha256": selected_set_sha256,
        "issues": issues,
        "stale_candidates": stale,
        "ok": ok,
    }


def dailies_review_status(root: Path | str) -> dict[str, Any]:
    """Validate Stage 7 review coverage without requiring Stage 8 selects."""
    base = Path(root).expanduser().resolve()
    report = read_json(base / "receipts" / "dailies.json") or {}
    spec = read_json(base / "film-spec.json") or {}
    planned = [
        str(shot.get("id") or shot.get("shot_id") or "").strip()
        for shot in iter_film_spec_shots(spec)
        if str(shot.get("id") or shot.get("shot_id") or "").strip()
    ]
    shots = report.get("shots") if isinstance(report.get("shots"), dict) else {}
    issues: list[dict[str, str]] = []
    for shot_id in planned:
        items = _current_items(shots.get(shot_id) if isinstance(shots.get(shot_id), list) else [])
        if not items:
            issues.append({"shot_id": shot_id, "code": "DAILIES_SHOT_MISSING"})
            continue
        for item in items:
            status = str(item.get("status") or "")
            candidate = Path(str(item.get("candidate") or ""))
            if not candidate.is_absolute():
                candidate = base / candidate
            if status not in STATUSES:
                issues.append({"shot_id": shot_id, "code": "DAILIES_TAKE_UNCLASSIFIED"})
            if not str(item.get("reviewer") or "").strip():
                issues.append({"shot_id": shot_id, "code": "DAILIES_REVIEWER_MISSING"})
            if status == "reject" and not str(item.get("notes") or "").strip():
                issues.append({"shot_id": shot_id, "code": "DAILIES_REJECT_REASON_MISSING"})
            if not candidate.is_file() or item.get("media_sha256") != _sha(candidate):
                issues.append({"shot_id": shot_id, "code": "DAILIES_MEDIA_STALE"})
    return {
        "kind": "dailies-review-status",
        "planned_shot_ids": planned,
        "issues": issues,
        "ok": bool(planned) and not issues,
    }
