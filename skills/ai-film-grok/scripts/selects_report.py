#!/usr/bin/env python3
"""Selects report: planned shots vs approved clips (craft ring 6)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def build_selects_report(root: Path, *, write_receipt: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    spec = _read_json(root / "film-spec.json")
    man = _read_json(root / "manifest.json")
    clips = man.get("clips") if isinstance(man.get("clips"), dict) else {}
    stills = man.get("stills") if isinstance(man.get("stills"), dict) else {}
    shots = spec.get("shots") if isinstance(spec.get("shots"), list) else []

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
        if status == "approved":
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
                "has_still": bool(still),
                "dramatic_function": shot.get("dramatic_function"),
                "shot_role": shot.get("shot_role"),
            }
        )

    planned = len(rows)
    report = {
        "ok": planned == 0 or (approved >= planned and missing == 0),
        "kind": "ai-film-selects-report",
        "schema_version": 1,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "root": str(root),
        "planned": planned,
        "approved": approved,
        "pending": pending,
        "missing": missing,
        "complete": planned > 0 and approved >= planned and missing == 0,
        "shots": rows,
        "note": "有文件 ≠ selects；须 register + identity/motion approved。见 craft-spine selects。",
    }
    if write_receipt:
        out = root / "receipts" / "selects-report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["receipt_path"] = str(out)
    return report
