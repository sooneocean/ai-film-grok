"""Human-attested anatomy safety gates for adult-max media.

The gate deliberately does not claim that text or a hash can recognise anatomy.
It records the required full-frame human inspection and fails closed when that
inspection is missing or has found a poisoned frame.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from util import read_json


class AnatomySafetyError(ValueError):
    pass


def requires_anatomy_safety(root: Path) -> bool:
    """Return whether this film's adult-max contract requires the attestation."""
    spec = read_json(Path(root).expanduser().resolve() / "film-spec.json") or {}
    return (
        isinstance(spec, dict)
        and str(spec.get("heat_scale") or "").strip().lower() == "max"
        and spec.get("adult_max_iron") is not False
    )


def require_anatomy_safe(*, root: Path, anatomy_safe: bool, kind: str, shot_id: str) -> None:
    """Require an explicit human attestation before approving adult-max media."""
    if not requires_anatomy_safety(root) or anatomy_safe:
        return
    raise AnatomySafetyError(
        f"adult-max approved {kind} for {shot_id} requires --anatomy-safe after full-frame "
        "human inspection (no futa/wrong anatomy, milk spray, or neon-genital artifact)"
    )


def anatomy_safety_report(
    manifest: dict[str, Any], *, required_shot_ids: list[str], kind: str
) -> dict[str, Any]:
    """Return missing/poisoned approval attestations for a manifest media collection."""
    records = manifest.get(kind) if isinstance(manifest.get(kind), dict) else {}
    missing: list[str] = []
    poisoned: list[str] = []
    for shot_id in required_shot_ids:
        record = records.get(shot_id)
        if not isinstance(record, dict) or record.get("status") != "approved":
            continue
        safe = record.get("anatomy_safe")
        if safe is True:
            continue
        if safe is False:
            poisoned.append(str(shot_id))
        else:
            missing.append(str(shot_id))
    ok = not missing and not poisoned
    return {
        "ok": ok,
        "kind": kind,
        "missing_attestation_shots": sorted(missing),
        "poisoned_shots": sorted(poisoned),
        "judgment_source": "human_full_frame_inspection",
        "reason": (
            "all approved media has anatomy_safe=true"
            if ok
            else "poisoned media must not enter I2V/register/final; missing attestation fails closed"
        ),
    }
