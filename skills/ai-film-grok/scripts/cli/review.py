"""Review control-plane command implementations independent of argparse dispatch."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shot_review import REVIEW_DIMENSIONS, create_shot_review


def create_shot_review_report(args: Any) -> dict[str, Any]:
    scores = {dim: getattr(args, f"score_{dim}") for dim in REVIEW_DIMENSIONS}
    return create_shot_review(
        Path(args.root),
        shot_id=str(args.shot_id),
        source=Path(args.source),
        reviewer=str(args.reviewer),
        notes=str(args.notes),
        scores=scores,
        evidence_values=list(args.evidence or []),
        references=[Path(item) for item in (args.reference or [])],
        approve=bool(args.approve),
    )


def migrate_review_contract(manifest: dict[str, Any]) -> tuple[list[str], str]:
    """Upgrade gates without treating historical boolean approvals as new evidence."""
    legacy = [
        sid
        for sid, record in (manifest.get("clips") or {}).items()
        if isinstance(record, dict)
        and record.get("status") == "approved"
        and not isinstance(record.get("shot_review"), dict)
    ]
    migrated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest["review_contract_version"] = 2
    manifest["review_contract_migrated_at"] = migrated_at
    manifest["review_contract_pending_shots"] = legacy
    return legacy, migrated_at
