"""Official final plate vs master classification (suse EP01 A5 · 2026-08-06)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Align with i2v_motion_gate.MEAN_MEAT_FLOOR (hard-defaults meat ≥20)
PLATE_BORING_MEAT_FLOOR = 20.0
PLATE_BORING_WEAK_RATIO = 0.50
PLATE_BORING_RECEIPT = "plate-boring-mean.json"


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


def assess_plate_boring_meat_mean(root: Path | str | None = None) -> dict[str, Any]:
    """I1.3 · meat mean largely below floor → not master-eligible (plate-boring).

    Reads ``receipts/i2v-high-motion-audit.json``. Boring when:
    - ``meat_mean_avg`` < 20, or
    - ≥50% of meat-tier shots have mean < 20

    Escape: ``AIFILM_SKIP_PLATE_BORING=1``.
    Missing audit → not boring (skipped; motion gate still separate).
    """
    if os.environ.get("AIFILM_SKIP_PLATE_BORING", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return {
            "kind": "plate-boring-mean",
            "ok": True,
            "boring": False,
            "skipped": True,
            "escape": "AIFILM_SKIP_PLATE_BORING=1",
            "codes": [],
        }
    if root is None:
        return {
            "kind": "plate-boring-mean",
            "ok": True,
            "boring": False,
            "skipped": True,
            "reason": "no_root",
            "codes": [],
        }
    root_p = Path(root).expanduser().resolve()
    try:
        from util import read_json
    except ImportError:  # pragma: no cover
        read_json = None  # type: ignore
    audit: dict[str, Any] = {}
    if read_json is not None:
        raw = read_json(root_p / "receipts" / "i2v-high-motion-audit.json")
        if isinstance(raw, dict):
            audit = raw
    if not audit:
        return {
            "kind": "plate-boring-mean",
            "ok": True,
            "boring": False,
            "skipped": True,
            "reason": "no_i2v_high_motion_audit",
            "codes": [],
        }
    meat_avg = audit.get("meat_mean_avg")
    per = audit.get("per_shot") if isinstance(audit.get("per_shot"), list) else []
    meat_rows: list[dict[str, Any]] = []
    for row in per:
        if not isinstance(row, dict):
            continue
        tier = str(row.get("tier") or "").lower()
        floor = row.get("floor")
        try:
            floor_f = float(floor) if floor is not None else None
        except (TypeError, ValueError):
            floor_f = None
        if tier in {"meat", "high"} or (floor_f is not None and floor_f + 1e-9 >= PLATE_BORING_MEAT_FLOOR):
            meat_rows.append(row)
    weak = 0
    for row in meat_rows:
        try:
            m = float(row.get("mean")) if row.get("mean") is not None else None
        except (TypeError, ValueError):
            m = None
        if m is None or m + 1e-9 < PLATE_BORING_MEAT_FLOOR:
            weak += 1
    weak_ratio = (weak / len(meat_rows)) if meat_rows else 0.0
    avg_low = False
    try:
        if meat_avg is not None and float(meat_avg) + 1e-9 < PLATE_BORING_MEAT_FLOOR:
            avg_low = True
    except (TypeError, ValueError):
        avg_low = False
    boring = bool(avg_low or (meat_rows and weak_ratio + 1e-9 >= PLATE_BORING_WEAK_RATIO))
    codes = ["PLATE_BORING_MEAT_MEAN"] if boring else []
    return {
        "kind": "plate-boring-mean",
        "ok": not boring,
        "boring": boring,
        "skipped": False,
        "meat_mean_avg": meat_avg,
        "meat_shot_count": len(meat_rows),
        "weak_meat_count": weak,
        "weak_ratio": round(weak_ratio, 3),
        "floor": PLATE_BORING_MEAT_FLOOR,
        "weak_ratio_floor": PLATE_BORING_WEAK_RATIO,
        "codes": codes,
        "note": (
            "meat mean largely below 20 → OFFICIAL_FINAL_PLATE only; re-I2V before master"
            if boring
            else "meat mean envelope acceptable for plate-boring gate"
        ),
        "next": (
            [
                "aifilm i2v-motion-gate --root \"$ROOT\" --write",
                "re-I2V meat shots (mean≥20) then gate-auto",
            ]
            if boring
            else []
        ),
    }


def write_plate_boring_receipt(root: Path | str, payload: dict[str, Any] | None = None) -> Path:
    """Write receipts/plate-boring-mean.json."""
    root_p = Path(root).expanduser().resolve()
    rep = payload if isinstance(payload, dict) else assess_plate_boring_meat_mean(root_p)
    out = root_p / "receipts" / PLATE_BORING_RECEIPT
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        from util import write_json

        write_json(out, rep)
    except ImportError:  # pragma: no cover
        import json

        out.write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out


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
    plate_boring: bool | None = None,
    root: Path | str | None = None,
) -> dict[str, Any]:
    """Classify delivery: OFFICIAL_FINAL_PLATE vs technical final (never auto master_lock).

    Skip gates / red machine lane / incomplete final_complete → plate + PARTIAL.
    I1.3: plate_boring meat mean → plate + PARTIAL (never master).
    Human master_lock is never inferred here.
    """
    boring_rep: dict[str, Any] | None = None
    if plate_boring is None and root is not None:
        boring_rep = assess_plate_boring_meat_mean(root)
        plate_boring = bool(boring_rep.get("boring"))
    elif plate_boring is None:
        plate_boring = False

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
    if plate_boring:
        honest.append("plate_boring_meat_mean")

    # Any escape hatch or red machine lane → plate only
    plate = bool(
        skip_preflight
        or skip_heat_gate
        or allow_loop_risk
        or gate_auto_ok is False
        or cinematic_ok is False
        or not final_complete
        or plate_boring
    )
    status = "OFFICIAL_FINAL_PLATE" if plate else "TECHNICAL_FINAL"
    out: dict[str, Any] = {
        "kind": "official-final-report",
        "status": status,
        "partial": plate,
        "master_lock": False,
        "final_complete": bool(final_complete),
        "gate_auto_ok": gate_auto_ok,
        "cinematic_ok": cinematic_ok,
        "plate_boring": bool(plate_boring),
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
    if boring_rep is not None:
        out["plate_boring_report"] = {
            "meat_mean_avg": boring_rep.get("meat_mean_avg"),
            "weak_ratio": boring_rep.get("weak_ratio"),
            "codes": boring_rep.get("codes") or [],
        }
    return out


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
    boring = assess_plate_boring_meat_mean(root_p)
    if boring.get("boring"):
        is_plate = True
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
    if boring.get("boring") and final_complete:
        blocks = True
        codes.append("PLATE_BORING_MEAT_MEAN")
    elif boring.get("boring"):
        codes.append("PLATE_BORING_MEAT_MEAN")
    return {
        "kind": "plate_vs_master_advisory",
        "ok": not blocks,
        "advisory": True,
        "is_plate": is_plate or status == "OFFICIAL_FINAL_PLATE",
        "plate_boring": bool(boring.get("boring")),
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
                *(
                    ["re-I2V meat shots until mean≥20 (plate-boring)"]
                    if boring.get("boring")
                    else []
                ),
            ]
            if blocks or is_plate
            else []
        ),
    }
