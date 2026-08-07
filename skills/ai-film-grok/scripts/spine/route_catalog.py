#!/usr/bin/env python3
"""Load and validate registry/route-catalog.json (R1 routing single source)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json

VALID_KINDS = frozenset({"action", "skill", "cli"})
# tombstone = production-removed surface (e.g. post lipsync CLI) — keep for lookup, hide by default.
VALID_STATUS = frozenset(
    {"canonical", "legacy", "partial", "orphan", "deprecated", "tombstone"}
)
VALID_SPEND = frozenset({"local", "external", "paid", "none"})
VALID_APPROVAL = frozenset({"none", "human_required"})
# Hidden from default list_routes (clear mind); still loadable via include_* or status=.
_DEFAULT_HIDDEN_STATUS = frozenset({"tombstone", "deprecated"})


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def catalog_path() -> Path:
    return skill_dir() / "registry" / "route-catalog.json"


def load_catalog() -> dict[str, Any]:
    path = catalog_path()
    data = read_json(path)
    if not data:
        return {
            "schema_version": 1,
            "ok": False,
            "error": f"missing route catalog at {path}",
            "routes": [],
            "path": str(path),
        }
    data["path"] = str(path)
    data["validation"] = validate_catalog(data)
    data["ok"] = bool(data["validation"]["ok"])
    return data


def validate_catalog(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Structural + cross-ref checks. Does not execute film work."""
    path = catalog_path()
    raw = data if data is not None else (read_json(path) or {})
    errors: list[str] = []
    warnings: list[str] = []

    if int(raw.get("schema_version") or 0) != 1:
        errors.append("schema_version must be 1")

    routes = raw.get("routes")
    if not isinstance(routes, list) or not routes:
        errors.append("routes must be a non-empty list")
        return {"ok": False, "errors": errors, "warnings": warnings, "counts": {}}

    ids: set[str] = set()
    for i, route in enumerate(routes):
        if not isinstance(route, dict):
            errors.append(f"routes[{i}] not an object")
            continue
        rid = str(route.get("id") or "").strip()
        if not rid:
            errors.append(f"routes[{i}] missing id")
            continue
        if rid in ids:
            errors.append(f"duplicate route id: {rid}")
        ids.add(rid)
        kind = str(route.get("kind") or "")
        if kind not in VALID_KINDS:
            errors.append(f"{rid}: invalid kind {kind!r}")
        status = str(route.get("status") or "")
        if status and status not in VALID_STATUS:
            errors.append(f"{rid}: invalid status {status!r}")
        spend = str(route.get("spend_class") or "local")
        if spend not in VALID_SPEND:
            errors.append(f"{rid}: invalid spend_class {spend!r}")
        approval = str(route.get("approval_class") or "none")
        if approval not in VALID_APPROVAL:
            errors.append(f"{rid}: invalid approval_class {approval!r}")

    # Cross-ref skills.json
    reg_path = skill_dir() / "registry" / "skills.json"
    reg = read_json(reg_path) or {}
    skill_ids = {
        str(s.get("id"))
        for s in (reg.get("skills") or [])
        if isinstance(s, dict) and s.get("id")
    }
    for route in routes:
        if not isinstance(route, dict):
            continue
        sid = route.get("skill_id")
        if sid and str(sid) not in skill_ids and route.get("status") != "orphan":
            # allow unskilled null; warn if set but missing
            if str(sid) not in skill_ids:
                warnings.append(f"{route.get('id')}: skill_id {sid!r} not in skills.json")

    # Advance subset: every advance_eligible action should have kind=action
    for route in routes:
        if not isinstance(route, dict):
            continue
        if route.get("advance_eligible") and route.get("kind") != "action":
            warnings.append(
                f"{route.get('id')}: advance_eligible=true but kind!={route.get('kind')!r}"
            )

    counts = {
        "routes": len(routes),
        "by_kind": {},
        "advance_eligible": sum(
            1 for r in routes if isinstance(r, dict) and r.get("advance_eligible")
        ),
        "hub_if_ladder": sum(
            1 for r in routes if isinstance(r, dict) and r.get("hub_if_ladder")
        ),
    }
    for r in routes:
        if isinstance(r, dict):
            k = str(r.get("kind") or "?")
            counts["by_kind"][k] = counts["by_kind"].get(k, 0) + 1

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": counts,
    }


def list_routes(
    *,
    kind: str | None = None,
    advance_only: bool = False,
    status: str | None = None,
    include_tombstones: bool = False,
    include_deprecated: bool = False,
    include_hidden: bool = False,
) -> list[dict[str, Any]]:
    """List routes for agents/CLI.

    Default **hides** ``tombstone`` and ``deprecated`` so retired surfaces
    (post lipsync, etc.) do not pollute default menus. Pass
    ``include_tombstones=True`` / ``include_hidden=True`` or filter
    ``status="tombstone"`` to inspect them.
    """
    cat = load_catalog()
    out: list[dict[str, Any]] = []
    want_status = str(status or "").strip() or None
    show_tomb = include_tombstones or include_hidden or want_status == "tombstone"
    show_dep = include_deprecated or include_hidden or want_status == "deprecated"
    for route in cat.get("routes") or []:
        if not isinstance(route, dict):
            continue
        if kind and route.get("kind") != kind:
            continue
        if advance_only and not route.get("advance_eligible"):
            continue
        st = str(route.get("status") or "")
        if want_status:
            if st != want_status:
                continue
        else:
            if st == "tombstone" and not show_tomb:
                continue
            if st == "deprecated" and not show_dep:
                continue
        out.append(route)
    return out


def get_route(route_id: str) -> dict[str, Any] | None:
    rid = str(route_id or "").strip()
    # Include hidden statuses so dispatch/CLI identity lookups still resolve tombstones.
    for route in list_routes(include_hidden=True):
        if route.get("id") == rid:
            return route
    return None
