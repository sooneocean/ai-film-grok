"""Bind planned shot actions to timestamped human review evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from performance_evidence import find_shot, performance_contract
from util import read_json, write_json


def build_beat_action_evidence(root: Path, *, write: bool = True) -> dict[str, Any]:
    root = Path(root).expanduser().resolve()
    spec = read_json(root / "film-spec.json") or {}
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for shot in scene.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            sid = str(shot.get("id") or "")
            if not sid:
                continue
            _, required = find_shot(root, sid)
            contract = performance_contract(shot, required=required or True)
            requirements = contract.get("requirements") or []
            action_requirements = [
                item
                for item in requirements
                if isinstance(item, dict)
                and item.get("kind") in {"action_visible", "trigger_visible", "reaction_visible"}
            ]
            review = read_json(root / "receipts" / "reviews" / f"{sid}.json") or {}
            evidence = (review.get("performance_contract") or {}).get("evidence") or {}
            required_kinds = sorted({str(item.get("kind")) for item in action_requirements})
            missing = [kind for kind in required_kinds if kind not in evidence]
            row = {
                "shot_id": sid,
                "beat_id": shot.get("beat_id") or shot.get("beatRef"),
                "planned_action": (shot.get("performance") or {}).get("playable_action")
                or (shot.get("content_channels") or {})
                .get("performance", {})
                .get("playable_action")
                or shot.get("action"),
                "required_kinds": required_kinds,
                "evidence": evidence,
                "review_approved": review.get("approved") is True,
                "ok": not missing and review.get("approved") is True,
            }
            rows.append(row)
            if missing:
                errors.append(
                    {
                        "code": "BEAT_ACTION_EVIDENCE_MISSING",
                        "shot_id": sid,
                        "message": ", ".join(missing),
                    }
                )
            if action_requirements and review.get("approved") is not True:
                errors.append(
                    {
                        "code": "BEAT_ACTION_REVIEW_NOT_APPROVED",
                        "shot_id": sid,
                        "message": "planned action lacks an approved shot review",
                    }
                )
    report = {
        "schema_version": 1,
        "kind": "beat-action-evidence",
        "ok": not errors,
        "required": bool(rows),
        "shots": rows,
        "errors": errors,
        "judgment_source": "human_observation",
        "limitation": "This report proves timestamped human observation, not automatic acting recognition.",
    }
    if write:
        path = root / "receipts" / "beat-action-evidence.json"
        write_json(path, report)
        report["path"] = str(path)
    return report
