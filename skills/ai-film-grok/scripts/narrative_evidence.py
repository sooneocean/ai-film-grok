"""Plan-vs-executed evidence for episode hooks and plot points."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from narrative_control import validate_narrative_graph
from util import read_json, write_json

EVIDENCE_NAME = "narrative-evidence.json"
VALID_STATUSES = frozenset({"verified", "missing", "uncertain"})


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _planned(graph: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    points = {
        str(p.get("point_id")): p for p in graph.get("plot_points") or [] if isinstance(p, dict)
    }
    for ep in graph.get("episodes") or []:
        if not isinstance(ep, dict):
            continue
        episode_id = str(ep.get("id") or "")
        for kind, hook in (
            ("opening_hook", ep.get("opening_hook")),
            ("ending_hook", ep.get("ending_hook")),
        ):
            if isinstance(hook, dict):
                point = points.get(str(hook.get("point_id"))) or {}
                rows.append(
                    {
                        "evidence_id": f"{episode_id}:{kind}",
                        "episode_id": episode_id,
                        "kind": kind,
                        "point_id": hook.get("point_id"),
                        "beat_id": hook.get("beat_id"),
                        "shot_ids": list(hook.get("shot_ids") or []),
                        "question": hook.get("question") or point.get("audience_question") or "",
                        "visible_evidence": point.get("visible_evidence") or "",
                    }
                )
        for point_id in ep.get("mid_episode_points") or []:
            point = points.get(str(point_id)) or {}
            rows.append(
                {
                    "evidence_id": f"{episode_id}:mid:{point_id}",
                    "episode_id": episode_id,
                    "kind": "mid_episode_point",
                    "point_id": point_id,
                    "beat_id": point.get("introduced_beat_id"),
                    "shot_ids": list(point.get("introduced_shot_ids") or []),
                    "question": point.get("audience_question") or "",
                    "visible_evidence": point.get("visible_evidence") or "",
                }
            )
    return rows


def build_narrative_evidence(root: Path, *, write: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    graph = read_json(root / "drama-graph.json") or {}
    existing = read_json(root / EVIDENCE_NAME) or {}
    planned = _planned(graph)
    prior = {
        str(item.get("evidence_id")): item
        for item in existing.get("items") or []
        if isinstance(item, dict) and item.get("evidence_id")
    }
    items: list[dict[str, Any]] = []
    for item in planned:
        old = prior.get(str(item["evidence_id"]), {})
        merged = {
            **item,
            "executed": old.get("executed") or {},
            "human_review": old.get("human_review") or {},
        }
        status = str(old.get("evidence_status") or "missing")
        merged["evidence_status"] = status if status in VALID_STATUSES else "uncertain"
        items.append(merged)
    report = {
        "schema_version": 1,
        "kind": "narrative-evidence",
        "at": _now(),
        "planned": planned,
        "items": items,
        "policy": graph.get("narrative_policy") or {},
    }
    if write:
        write_json(root / EVIDENCE_NAME, report)
    return report


def validate_narrative_evidence(root: Path, *, require_verified: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    graph = read_json(root / "drama-graph.json") or {}
    semantic = (
        validate_narrative_graph(graph, strict=True) if graph else {"ok": False, "issues": []}
    )
    report = read_json(root / EVIDENCE_NAME) or {}
    items = [item for item in report.get("items") or [] if isinstance(item, dict)]
    expected = _planned(graph)
    by_id = {str(item.get("evidence_id")): item for item in items}
    issues: list[dict[str, Any]] = []
    for planned in expected:
        item = by_id.get(str(planned["evidence_id"]))
        if not item:
            issues.append(
                {
                    "code": "NARRATIVE_EVIDENCE_MISSING",
                    "message": f"missing evidence item: {planned['evidence_id']}",
                }
            )
            continue
        if require_verified and item.get("evidence_status") != "verified":
            issues.append(
                {
                    "code": "NARRATIVE_EVIDENCE_UNVERIFIED",
                    "message": f"narrative evidence is not verified: {planned['evidence_id']}",
                }
            )
        executed = item.get("executed") if isinstance(item.get("executed"), dict) else {}
        human = item.get("human_review") if isinstance(item.get("human_review"), dict) else {}
        if require_verified and (not executed or human.get("approved") is not True):
            issues.append(
                {
                    "code": "NARRATIVE_EXECUTED_EVIDENCE_MISSING",
                    "message": f"executed and human evidence required: {planned['evidence_id']}",
                }
            )
    issues.extend(semantic.get("errors") or [])
    return {
        "ok": not issues,
        "required": bool(graph.get("narrative_policy", {}).get("require_executed_evidence", True)),
        "planned_count": len(expected),
        "verified_count": sum(1 for item in items if item.get("evidence_status") == "verified"),
        "issues": issues,
        "path": str(root / EVIDENCE_NAME),
    }
