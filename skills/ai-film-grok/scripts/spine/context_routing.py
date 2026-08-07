#!/usr/bin/env python3
"""Select a small, deterministic set of stage references for one agent turn."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# scripts/spine/ → skill package root is two parents up (was scripts/ top-level).
SKILL_ROOT = Path(__file__).resolve().parents[2]
ROUTING_PATH = SKILL_ROOT / "registry" / "context-routing.json"


def load_context_routing(path: Path = ROUTING_PATH) -> dict[str, Any]:
    from util import require_json_fnv

    data = require_json_fnv(path)
    if int(data.get("schema_version") or 0) != 1:
        raise ValueError("context routing schema_version must be 1")
    return data


def _entries(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def select_context_refs(
    *,
    craft_stage: str,
    pipeline_stage: str,
    skill_id: str = "",
    issue_codes: list[str] | None = None,
    routing: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return existing references within the configured count and byte budgets."""
    cfg = routing or load_context_routing()
    candidates: list[dict[str, Any]] = []
    for code in issue_codes or []:
        candidates.extend(_entries((cfg.get("issues") or {}).get(str(code))))
    candidates.extend(_entries((cfg.get("skills") or {}).get(skill_id)))
    candidates.extend(_entries((cfg.get("pipeline_stages") or {}).get(pipeline_stage)))
    candidates.extend(_entries((cfg.get("stages") or {}).get(craft_stage)))

    max_refs = max(1, int(cfg.get("max_refs") or 3))
    max_bytes = max(1, int(cfg.get("max_bytes") or 8192))
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    used_bytes = 0
    for item in candidates:
        rel = str(item.get("path") or "").strip()
        if not rel or rel in seen:
            continue
        path = (SKILL_ROOT / rel).resolve()
        if SKILL_ROOT not in path.parents or not path.is_file():
            continue
        size = path.stat().st_size
        if selected and used_bytes + size > max_bytes:
            continue
        selected.append(
            {
                "path": rel,
                "reason": str(item.get("reason") or ""),
                "required": bool(item.get("required", False)),
                "bytes": size,
            }
        )
        seen.add(rel)
        used_bytes += size
        if len(selected) >= max_refs:
            break
    return selected
