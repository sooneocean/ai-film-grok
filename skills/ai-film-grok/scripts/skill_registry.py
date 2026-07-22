#!/usr/bin/env python3
"""Skill Registry loader for ai-film-grok (Phase 2 shell).

Registry is the enumerable capability list for Agents.
Implementation still maps to existing CLI / modules.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from util import read_json

VALID_STATUSES = frozenset(
    {"implemented", "partial", "stub", "human_required", "blocked", "deprecated"}
)


def skill_dir() -> Path:
    """skills/ai-film-grok root (parent of scripts/)."""
    return Path(__file__).resolve().parents[1]


def registry_path() -> Path:
    return skill_dir() / "registry" / "skills.json"


def contracts_dir() -> Path:
    return skill_dir() / "registry" / "contracts"


def load_registry() -> dict[str, Any]:
    path = registry_path()
    data = read_json(path)
    if not data:
        return {
            "schema_version": 1,
            "skills": [],
            "error": f"missing registry at {path}",
            "ok": False,
        }
    for skill in data.get("skills") or []:
        if not isinstance(skill, dict):
            continue
        cli = skill.get("cli") if isinstance(skill.get("cli"), dict) else {}
        validator = cli.get("validate")
        skill.setdefault(
            "executionContract",
            {
                "input": skill.get("inputContract") or "registry/contracts/skill-envelope.in.json",
                "output": skill.get("outputContract")
                or "registry/contracts/skill-envelope.out.json",
                "validator": validator,
                "sideEffects": "external_media_or_filesystem"
                if str(skill.get("id") or "").split(".", 1)[0]
                in {"image", "keyframe", "voice", "sound", "music", "timeline", "video", "export"}
                else "filesystem_or_receipt",
                "humanApprovalRequired": skill.get("status") == "human_required"
                or str(skill.get("id") or "")
                in {"keyframe.generate", "image.animate", "quality.inspect", "export.package"},
                "retryPolicy": "explicit_requeue_only"
                if str(skill.get("id") or "") in {"image.animate", "voice.synthesize"}
                else "none",
            },
        )
    data["validation"] = validate_registry(data)
    data["ok"] = True
    data["path"] = str(path)
    return data


def list_skills(*, tag: str | None = None, phase: str | None = None) -> dict[str, Any]:
    reg = load_registry()
    skills = list(reg.get("skills") or [])
    if tag:
        skills = [s for s in skills if tag in (s.get("tags") or [])]
    if phase:
        skills = [s for s in skills if phase in (s.get("phases") or [])]
    return {
        "ok": bool(reg.get("ok")),
        "path": reg.get("path") or str(registry_path()),
        "count": len(skills),
        "skills": [
            {
                "id": s.get("id"),
                "version": s.get("version"),
                "summary": s.get("summary"),
                "status": s.get("status"),
                "produces": s.get("produces"),
                "cli": s.get("cli"),
                "tags": s.get("tags"),
                "executionContract": s.get("executionContract"),
                "contractComplete": bool((s.get("executionContract") or {}).get("validator")),
            }
            for s in skills
            if isinstance(s, dict)
        ],
        "error": reg.get("error"),
        "validation": reg.get("validation"),
    }


def validate_registry(registry: dict[str, Any]) -> dict[str, Any]:
    """Validate the registry as an executable capability contract."""
    errors: list[str] = []
    warnings: list[str] = []
    skills = registry.get("skills") if isinstance(registry, dict) else None
    if not isinstance(skills, list) or not skills:
        return {"ok": False, "errors": ["skills must be a non-empty array"], "warnings": []}
    seen: set[str] = set()
    incomplete: list[str] = []
    for skill in skills:
        if not isinstance(skill, dict):
            errors.append("skill entry must be an object")
            continue
        sid = str(skill.get("id") or "")
        if not sid:
            errors.append("skill.id is required")
            continue
        if sid in seen:
            errors.append(f"duplicate skill id: {sid}")
        seen.add(sid)
        status = str(skill.get("status") or "")
        if status not in VALID_STATUSES:
            errors.append(f"{sid}: invalid status={status!r}")
        contract = skill.get("executionContract") or {}
        if status == "implemented" and not contract.get("validator"):
            incomplete.append(sid)
    if incomplete:
        warnings.append("implemented skills missing validator: " + ", ".join(incomplete))
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "skill_count": len(seen),
        "implemented_without_validator": incomplete,
    }


def show_skill(skill_id: str) -> dict[str, Any]:
    reg = load_registry()
    for s in reg.get("skills") or []:
        if isinstance(s, dict) and s.get("id") == skill_id:
            # attach contract files if present
            contracts: dict[str, Any] = {}
            for key in ("inputContract", "outputContract"):
                rel = s.get(key)
                if not rel:
                    continue
                cpath = skill_dir() / rel if not str(rel).startswith("/") else Path(rel)
                if not cpath.is_file():
                    cpath = contracts_dir() / Path(rel).name
                if cpath.is_file():
                    try:
                        contracts[key] = json.loads(cpath.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError) as exc:
                        contracts[key] = {"error": str(exc)}
                else:
                    contracts[key] = {"missing": str(cpath)}
            return {
                "ok": True,
                "skill": s,
                "contracts": contracts,
                "registry_path": reg.get("path"),
            }
    return {
        "ok": False,
        "error": f"unknown skill_id={skill_id!r}",
        "hint": "aifilm skill list",
    }


def validate_skill_payload(
    skill_id: str, payload: dict[str, Any], *, direction: str = "input"
) -> dict[str, Any]:
    """Validate the minimum runtime envelope before a skill is dispatched."""
    skill = show_skill(skill_id)
    if not skill.get("ok"):
        return skill
    errors: list[str] = []
    if not isinstance(payload, dict):
        errors.append("payload must be an object")
    else:
        required = (
            ("skillId", "nodeRef", "inputHash")
            if direction == "input"
            else ("skillId", "nodeRef", "outputHash")
        )
        for key in required:
            if not str(payload.get(key) or "").strip():
                errors.append(f"{key} is required")
        if payload.get("skillId") and payload.get("skillId") != skill_id:
            errors.append("skillId does not match requested skill")
    return {"ok": not errors, "skill_id": skill_id, "direction": direction, "errors": errors}


def skill_ids() -> list[str]:
    reg = load_registry()
    return [
        str(s.get("id")) for s in (reg.get("skills") or []) if isinstance(s, dict) and s.get("id")
    ]


def map_cli_to_skills() -> dict[str, list[str]]:
    """Reverse index: CLI verb → skill ids (for docs / CI)."""
    out: dict[str, list[str]] = {}
    for s in load_registry().get("skills") or []:
        if not isinstance(s, dict):
            continue
        cli = s.get("cli") or {}
        run = str(cli.get("run") or "")
        if not run:
            continue
        # first token after aifilm if present
        token = run.split()[0] if run.startswith("aifilm") is False else (run.split() + [""])[1]
        if run.startswith("aifilm"):
            parts = run.split()
            token = parts[1] if len(parts) > 1 else "aifilm"
        out.setdefault(token, []).append(str(s.get("id")))
    return out
