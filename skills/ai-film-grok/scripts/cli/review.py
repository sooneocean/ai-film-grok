"""Review control-plane command implementations independent of argparse dispatch."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shot_review import create_shot_review


def create_shot_review_report(args: Any) -> dict[str, Any]:
    # CORE dims required; optional coitus only if CLI provided (少婦案 AttributeError)
    from shot_review import CORE_REVIEW_DIMENSIONS

    scores = {dim: getattr(args, f"score_{dim}") for dim in CORE_REVIEW_DIMENSIONS}
    coitus = getattr(args, "score_coitus", None)
    if coitus is not None:
        scores["coitus"] = coitus
    return create_shot_review(
        Path(args.root),
        shot_id=str(args.shot_id),
        source=Path(args.source),
        reviewer=str(args.reviewer),
        notes=str(args.notes),
        scores=scores,
        evidence_values=list(args.evidence or []),
        performance_evidence_values=list(args.performance_evidence or []),
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
    migrated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    manifest["review_contract_version"] = 2
    manifest["review_contract_migrated_at"] = migrated_at
    manifest["review_contract_pending_shots"] = legacy
    return legacy, migrated_at
