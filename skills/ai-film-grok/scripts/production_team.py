#!/usr/bin/env python3
"""Evidence-bound specialist-director roster for one film workspace.

This is deliberately an orchestration contract, not an autonomous agent runner.
It makes model ownership, review authority, and handoff evidence explicit before
any model is asked to make or modify media.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from production_router import RouteExplainError, _validate_snapshot
from util import canonical_json_sha256, read_json, sha256_file, utc_now, write_json


class ProductionTeamError(ValueError):
    """A production-team plan is missing, malformed, or no longer current."""


TEAM_VERSION = 1
DIRECTORS: tuple[dict[str, Any], ...] = (
    {
        "id": "showrunner",
        "department": "story",
        "mandate": "Protect theme, character arc, scene objective, and script lock.",
        "model_jobs": ["local LLM critique", "continuity graph analysis"],
        "must_review": ["brief.json", "drama-graph.json", "film-spec.json"],
    },
    {
        "id": "cinematography",
        "department": "visual",
        "mandate": "Protect style, framing, identity, lighting, and reachable shot endpoints.",
        "model_jobs": ["prompt critique", "still and motion generation"],
        "must_review": ["style-bible.json", "shot visual direction", "review-shot receipt"],
    },
    {
        "id": "performance",
        "department": "performance",
        "mandate": "Protect acting beats, dialogue timing, voice identity, and truthful lip sync.",
        "model_jobs": ["TTS rehearsal", "lip-sync pilot"],
        "must_review": ["tts-rehearsal receipt", "shot performance", "lip-sync review"],
    },
    {
        "id": "sound",
        "department": "sound",
        "mandate": "Protect intelligible dialogue, concrete foley, changing music, and final mix audibility.",
        "model_jobs": ["voice synthesis", "music and SFX generation"],
        "must_review": ["audio-bible.json", "mix report", "quiet-interval music check"],
    },
    {
        "id": "editor",
        "department": "post",
        "mandate": "Protect shot selection, rhythm, subtitles, transitions, and picture lock.",
        "model_jobs": ["selects analysis", "deterministic finishing"],
        "must_review": ["dailies receipt", "rough-cut receipt", "post-bible.json"],
    },
    {
        "id": "quality",
        "department": "delivery",
        "mandate": "Reject weak evidence; require decoded media, whole-film review, and current provenance.",
        "model_jobs": ["frame and audio QA", "delivery audit"],
        "must_review": ["ffprobe", "full decode", "final human director review"],
    },
)
_DIRECTOR_IDS = frozenset(item["id"] for item in DIRECTORS)


def _snapshot(path: Path | str) -> tuple[Path, dict[str, Any]]:
    candidate = Path(path).expanduser().resolve()
    value = read_json(candidate)
    if not isinstance(value, dict):
        raise ProductionTeamError(f"CAPABILITY_SNAPSHOT_MISSING: {candidate}")
    try:
        _validate_snapshot(value)
    except RouteExplainError as exc:
        raise ProductionTeamError(str(exc)) from exc
    return candidate, value


def scaffold_team(
    root: Path | str,
    *,
    capabilities_path: Path | str,
    out: Path | str | None = None,
) -> dict[str, Any]:
    """Write a no-execution team plan with one named accountable director per craft."""
    base = Path(root).expanduser().resolve()
    snapshot_path, snapshot = _snapshot(capabilities_path)
    destination = Path(out).expanduser().resolve() if out else base / "production-team.json"
    capabilities = snapshot["capabilities"]
    assignments = [
        {
            "director_id": director["id"],
            "model_capability_ids": [],
            "local_tools": [],
            "human_review_required": True,
        }
        for director in DIRECTORS
    ]
    plan: dict[str, Any] = {
        "schema_version": TEAM_VERSION,
        "kind": "ai-film-production-team",
        "created_at": utc_now(),
        "root": str(base),
        "capability_snapshot": {"path": str(snapshot_path), "sha256": sha256_file(snapshot_path)},
        "directors": list(DIRECTORS),
        "assignments": assignments,
        "available_capabilities": [
            {key: item[key] for key in ("id", "provider", "model", "resource", "status")}
            for item in capabilities
        ],
        "auto_execute": False,
        "notes": [
            "Assign only pilot-verified, currently ready model capability IDs.",
            "M1 and LAN 5090 tools must be named explicitly; a declared local tool is not readiness proof.",
            "Each specialist advises and validates; human approval remains required at lock and spend boundaries.",
        ],
    }
    plan["content_sha256"] = canonical_json_sha256(plan)
    write_json(destination, plan)
    return {"ok": True, "written": str(destination), "plan": plan}


def validate_team(plan_path: Path | str, *, capabilities_path: Path | str) -> dict[str, Any]:
    """Fail closed when a specialist lacks an owner or references stale model evidence."""
    plan_file = Path(plan_path).expanduser().resolve()
    plan = read_json(plan_file)
    if not isinstance(plan, dict) or plan.get("kind") != "ai-film-production-team":
        raise ProductionTeamError(f"TEAM_PLAN_MISSING_OR_INVALID: {plan_file}")
    recorded_hash = plan.get("content_sha256")
    unsigned = {key: value for key, value in plan.items() if key != "content_sha256"}
    if recorded_hash != canonical_json_sha256(unsigned):
        raise ProductionTeamError("TEAM_PLAN_HASH_MISMATCH")
    snapshot_path, snapshot = _snapshot(capabilities_path)
    snapshot_ref = (
        plan.get("capability_snapshot") if isinstance(plan.get("capability_snapshot"), dict) else {}
    )
    blockers: list[str] = []
    if snapshot_ref.get("sha256") != sha256_file(snapshot_path):
        blockers.append("CAPABILITY_SNAPSHOT_CHANGED")
    assignments = plan.get("assignments")
    if not isinstance(assignments, list):
        raise ProductionTeamError("TEAM_ASSIGNMENTS_INVALID")
    by_director: dict[str, dict[str, Any]] = {}
    for item in assignments:
        if not isinstance(item, dict):
            blockers.append("TEAM_ASSIGNMENT_INVALID")
            continue
        director_id = str(item.get("director_id") or "")
        if director_id not in _DIRECTOR_IDS or director_id in by_director:
            blockers.append("DIRECTOR_ASSIGNMENT_INVALID")
            continue
        by_director[director_id] = item
    capabilities = {str(item["id"]): item for item in snapshot["capabilities"]}
    coverage: list[dict[str, Any]] = []
    for director in DIRECTORS:
        director_id = director["id"]
        assignment = by_director.get(director_id)
        if assignment is None:
            coverage.append(
                {"director_id": director_id, "ok": False, "blockers": ["DIRECTOR_UNASSIGNED"]}
            )
            blockers.append(f"DIRECTOR_UNASSIGNED:{director_id}")
            continue
        capability_ids = assignment.get("model_capability_ids")
        local_tools = assignment.get("local_tools")
        if not isinstance(capability_ids, list) or not isinstance(local_tools, list):
            coverage.append(
                {"director_id": director_id, "ok": False, "blockers": ["ASSIGNMENT_FIELDS_INVALID"]}
            )
            blockers.append(f"ASSIGNMENT_FIELDS_INVALID:{director_id}")
            continue
        reasons: list[str] = []
        if not capability_ids and not local_tools:
            reasons.append("NO_MODEL_OR_TOOL_ASSIGNED")
        for capability_id in capability_ids:
            capability = capabilities.get(str(capability_id))
            if capability is None:
                reasons.append(f"CAPABILITY_UNKNOWN:{capability_id}")
            elif (
                capability.get("status") != "ready" or capability.get("pilot_verified") is not True
            ):
                reasons.append(f"CAPABILITY_NOT_READY:{capability_id}")
        coverage.append({"director_id": director_id, "ok": not reasons, "blockers": reasons})
        blockers.extend(f"{reason}:{director_id}" for reason in reasons)
    blockers = sorted(set(blockers))
    return {
        "ok": not blockers,
        "kind": "ai-film-production-team-validation",
        "read_only": True,
        "auto_execute": False,
        "plan": str(plan_file),
        "capability_snapshot": str(snapshot_path),
        "coverage": coverage,
        "blockers": blockers,
    }
