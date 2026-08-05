"""Small, import-safe quality status surface for the main argparse CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json


def quality_contract_status(root: Path | str) -> dict[str, Any]:
    base = Path(root).expanduser().resolve()
    manifest = read_json(base / "manifest.json") or {}
    clips = manifest.get("clips") if isinstance(manifest.get("clips"), dict) else {}
    try:
        from quality_evidence import quality_evidence_is_current
    except ImportError:

        def quality_evidence_is_current(_evidence: object, *, clip: Path) -> bool:
            return False

    shots: dict[str, dict[str, bool]] = {}
    for shot_id, record in clips.items():
        if not isinstance(record, dict) or record.get("status") != "approved":
            continue
        path = Path(str(record.get("path") or ""))
        shots[str(shot_id)] = {
            "quality_evidence_current": quality_evidence_is_current(
                record.get("quality_evidence"), clip=path
            ),
            "motion_evidence_recorded": isinstance(record.get("motion_evidence"), dict),
            "review_recorded": isinstance(record.get("shot_review"), dict),
        }
    return {
        "kind": "quality-contract-status",
        "contract_version": int(manifest.get("quality_evidence_contract_version") or 0),
        "shots": shots,
        "ok": all(item["quality_evidence_current"] for item in shots.values()),
    }
