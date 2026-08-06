"""Official final plate vs master classification (suse EP01 A5 · 2026-08-06)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def read_gate_auto_ok(root: Path | str) -> bool | None:
    """Return True/False if gate-auto receipt present; None if missing."""
    try:
        from util import read_json
    except ImportError:  # pragma: no cover
        return None
    data = read_json(Path(root).expanduser().resolve() / "receipts" / "gate-auto.json")
    if not isinstance(data, dict) or not data:
        return None
    if "ok" in data:
        return bool(data.get("ok"))
    if "hard_ok" in data:
        return bool(data.get("hard_ok"))
    machine = data.get("machine_ready")
    if isinstance(machine, dict) and "ok" in machine:
        return bool(machine.get("ok"))
    return None


def classify_official_final(
    *,
    skip_preflight: bool = False,
    skip_heat_gate: bool = False,
    allow_loop_risk: bool = False,
    force: bool = False,
    gate_auto_ok: bool | None = None,
    cinematic_ok: bool | None = None,
    final_complete: bool = False,
    bgm_partial: bool = False,
) -> dict[str, Any]:
    """Classify delivery: OFFICIAL_FINAL_PLATE vs technical final (never auto master_lock).

    Skip gates / red machine lane / incomplete final_complete → plate + PARTIAL.
    Human master_lock is never inferred here.
    """
    honest: list[str] = []
    if skip_preflight:
        honest.append("skip_preflight")
    if skip_heat_gate:
        honest.append("skip_heat_gate")
    if allow_loop_risk:
        honest.append("allow_loop_risk")
    if force:
        honest.append("force_render")
    if gate_auto_ok is False:
        honest.append("gate_auto_red")
    if cinematic_ok is False:
        honest.append("cinematic_gate_red")
    if bgm_partial:
        honest.append("bgm_procedural_or_partial")
    if not final_complete:
        honest.append("final_complete_false")

    # Any escape hatch or red machine lane → plate only
    plate = bool(
        skip_preflight
        or skip_heat_gate
        or allow_loop_risk
        or gate_auto_ok is False
        or cinematic_ok is False
        or not final_complete
    )
    status = "OFFICIAL_FINAL_PLATE" if plate else "TECHNICAL_FINAL"
    return {
        "kind": "official-final-report",
        "status": status,
        "partial": plate,
        "master_lock": False,
        "final_complete": bool(final_complete),
        "gate_auto_ok": gate_auto_ok,
        "cinematic_ok": cinematic_ok,
        "honest_limits": honest
        or (
            ["technical render ok; human review-final still required for master"]
            if status == "TECHNICAL_FINAL"
            else []
        ),
        "not": ["master_lock", "human_approved_ship"],
        "note": (
            "plate ≠ master-lock; gate-auto green + human review-final required for ship complete"
            if plate
            else "technical final only — still not master_lock without human review"
        ),
    }


def write_official_final_report(root: Path | str, payload: dict[str, Any]) -> Path:
    """Write receipts/official-final-report.json."""
    root_p = Path(root).expanduser().resolve()
    out = root_p / "receipts" / "official-final-report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        from util import write_json

        write_json(out, payload)
    except ImportError:  # pragma: no cover
        import json

        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


def delivery_fields_from_official_final(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize manifest fields for final report/manifest reconciliation.

    Always materialize source + visibility so downstream consumers can treat
    manifest records without separate schema branches.
    """
    payload = payload or {}
    status = str(payload.get("status") or payload.get("delivery_class") or "").strip()
    if not status:
        status = "TECHNICAL_FINAL"
    visibility = payload.get("delivery_visibility")
    if visibility is None:
        if status == "OFFICIAL_FINAL_PLATE":
            visibility = "visible_plate"
        elif status == "TECHNICAL_FINAL":
            visibility = "technical_final_visible"
        else:
            visibility = str(payload.get("delivery_class") or status or "TECHNICAL_FINAL")
    return {
        "delivery_class": status,
        "delivery_source": "official_final_report",
        "delivery_visibility": str(visibility),
        "master_lock": bool(payload.get("master_lock", False)),
    }


def plate_blocks_final_complete(
    root: Path | str,
    *,
    gates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """S1.4 · plate / red gate must not be treated as final_complete master.

    Returns advisory when OFFICIAL_FINAL_PLATE or gate-auto red while someone
    might claim ship-complete.
    """
    root_p = Path(root).expanduser().resolve()
    try:
        from util import read_json
    except ImportError:  # pragma: no cover
        read_json = None  # type: ignore
    report = None
    if read_json is not None:
        report = read_json(root_p / "receipts" / "official-final-report.json")
    if not isinstance(report, dict):
        report = {}
    status = str(report.get("status") or "")
    master_claim = bool(report.get("master_lock"))
    gate_ok = read_gate_auto_ok(root_p)
    g = gates if isinstance(gates, dict) else {}
    final_complete = bool(g.get("final_complete"))
    is_plate = status == "OFFICIAL_FINAL_PLATE" or bool(report.get("partial"))
    blocks = False
    codes: list[str] = []
    if is_plate and final_complete:
        blocks = True
        codes.append("PLATE_CLAIMED_FINAL_COMPLETE")
    if master_claim:
        blocks = True
        codes.append("MASTER_LOCK_ON_PLATE_RECEIPT")
    if gate_ok is False and final_complete:
        blocks = True
        codes.append("GATE_AUTO_RED_WITH_FINAL_COMPLETE")
    return {
        "kind": "plate_vs_master_advisory",
        "ok": not blocks,
        "advisory": True,
        "is_plate": is_plate or status == "OFFICIAL_FINAL_PLATE",
        "final_complete": final_complete,
        "gate_auto_ok": gate_ok,
        "master_lock_claimed": master_claim,
        "codes": codes,
        "blocks_ship_complete": blocks,
        "note": (
            "OFFICIAL_FINAL_PLATE ≠ master; clear final_complete until gate-auto green + review-final"
            if blocks or is_plate
            else "no plate/master conflict detected"
        ),
        "next": (
            [
                "do not export-desktop as ship-complete while plate/PARTIAL",
                "aifilm gate-auto → review-final before final_complete",
            ]
            if blocks or is_plate
            else []
        ),
    }
