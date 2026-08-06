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
