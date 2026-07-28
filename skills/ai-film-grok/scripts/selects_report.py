#!/usr/bin/env python3
"""Selects report: planned shots vs approved clips (craft ring 6)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from util import read_json


def build_selects_report(root: Path, *, write_receipt: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    from dailies import dailies_status

    spec = read_json(root / "film-spec.json") or {}
    man = read_json(root / "manifest.json") or {}
    clips = man.get("clips") if isinstance(man.get("clips"), dict) else {}
    stills = man.get("stills") if isinstance(man.get("stills"), dict) else {}
    shots = spec.get("shots") if isinstance(spec.get("shots"), list) else []

    dailies = dailies_status(root)
    professional = (read_json(root / "production-book.json") or {}).get("rigor") == "professional"
    use_dailies = bool(dailies.get("planned_shot_ids")) and (
        professional or bool(read_json(root / "receipts" / "dailies.json"))
    )
    dailies_by_shot = {str(item.get("shot_id")): item for item in dailies.get("selections") or []}
    dailies_issues = {
        str(item.get("shot_id")): str(item.get("code")) for item in dailies.get("issues") or []
    }

    rows: list[dict[str, Any]] = []
    approved = 0
    pending = 0
    missing = 0
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        sid = str(shot.get("id") or shot.get("shot_id") or "").strip()
        if not sid:
            continue
        rec = clips.get(sid) if isinstance(clips.get(sid), dict) else {}
        still = stills.get(sid) if isinstance(stills.get(sid), dict) else {}
        status = str(rec.get("status") or "").lower()
        selected_take = dailies_by_shot.get(sid)
        if use_dailies and sid in dailies_issues:
            state = "invalid_select"
            pending += 1
        elif use_dailies and selected_take:
            state = "selected"
            approved += 1
        elif use_dailies:
            state = "missing"
            missing += 1
        elif status == "approved":
            state = "selected"
            approved += 1
        elif rec:
            state = "raw_or_pending"
            pending += 1
        else:
            state = "missing"
            missing += 1
        rows.append(
            {
                "shot_id": sid,
                "state": state,
                "clip_status": rec.get("status"),
                "source_endpoint": rec.get("source_endpoint") or rec.get("endpoint"),
                "identity_approved": rec.get("identity_approved"),
                "motion_approved": rec.get("motion_approved"),
                "selected_media_sha256": (selected_take or {}).get("media_sha256"),
                "select_issue": dailies_issues.get(sid),
                "has_still": bool(still),
                "dramatic_function": shot.get("dramatic_function"),
                "shot_role": shot.get("shot_role"),
            }
        )

    planned = len(rows)
    report = {
        "ok": planned == 0 or (approved >= planned and missing == 0 and not pending),
        "kind": "ai-film-selects-report",
        "schema_version": 1,
        "at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "root": str(root),
        "planned": planned,
        "approved": approved,
        "pending": pending,
        "missing": missing,
        "complete": planned > 0 and approved >= planned and missing == 0 and not pending,
        "canonical_ledger": "receipts/dailies.json" if use_dailies else "legacy-manifest",
        "selected_set_sha256": dailies.get("selected_set_sha256") if use_dailies else None,
        "shots": rows,
        "note": "有文件 ≠ selects；须 register + identity/motion approved。见 craft-spine selects。",
    }
    if write_receipt:
        out = root / "receipts" / "selects-report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["receipt_path"] = str(out)
    return report
