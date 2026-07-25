#!/usr/bin/env python3
"""Deterministically validate a project blueprint without generating media."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(root: Path, blueprint_path: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    path = blueprint_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    if not path.is_file():
        return {"ok": False, "errors": [f"missing blueprint: {path}"], "warnings": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "errors": [f"invalid blueprint JSON: {exc}"], "warnings": []}

    required = {"schema_version", "kind", "project", "story", "characters", "style", "continuity", "episodes", "handoff"}
    errors.extend(f"missing top-level field: {key}" for key in sorted(required - set(data)))
    if data.get("schema_version") != 1 or data.get("kind") != "ai-film-project-blueprint":
        errors.append("unsupported schema_version or kind")

    project = data.get("project") or {}
    if project.get("status") == "approved" and not project.get("lock_hash"):
        errors.append("approved project requires lock_hash")
    story = data.get("story") or {}
    if not isinstance(story.get("source_sha256"), str) or len(story["source_sha256"]) != 64:
        errors.append("story.source_sha256 must be a 64-character sha256")

    seen: set[str] = set()
    for char in data.get("characters") or []:
        cid = str(char.get("character_id") or "")
        if not cid or cid in seen:
            errors.append(f"duplicate or missing character_id: {cid or '<empty>'}")
        seen.add(cid)
        views = char.get("reference_views") or []
        view_ids = {str(view.get("view_id") or "") for view in views}
        master = char.get("canonical_master") or {}
        if master.get("view_id") not in view_ids:
            errors.append(f"{cid}: canonical_master.view_id is not in reference_views")
        if char.get("status") == "approved" and master.get("review_status") != "approved":
            errors.append(f"{cid}: approved character requires approved canonical_master")
        for view in views:
            raw_path = str(view.get("path") or "")
            candidate = (root / raw_path).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                errors.append(f"{cid}: reference path escapes project root: {raw_path}")
                continue
            if not candidate.is_file():
                errors.append(f"{cid}: missing reference file: {raw_path}")
            elif view.get("sha256") and _sha256(candidate) != view.get("sha256"):
                errors.append(f"{cid}:{view.get('view_id')}: sha256 changed")

    style = data.get("style") or {}
    if style.get("status") == "approved" and not data.get("project", {}).get("lock_hash"):
        warnings.append("style is approved but project lock_hash is absent")
    if not (data.get("episodes") or []):
        warnings.append("no episode is registered yet; blueprint is reusable but not episode-ready")
    handoff = data.get("handoff") or {}
    for field in ("project_lock_fields", "episode_fields", "approval_required"):
        if not isinstance(handoff.get(field), list) or not handoff[field]:
            errors.append(f"handoff.{field} must be a non-empty list")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "character_count": len(seen)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--blueprint", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = validate(args.root, args.blueprint)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
