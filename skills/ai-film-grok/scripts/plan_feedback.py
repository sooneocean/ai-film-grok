"""Execution feedback loop — derive planning adjustments from narrative evidence.

Reads narrative-evidence.json (planned vs executed) and produces
actionable adjustments for future planning runs:
- Beat duration adjustments (planned vs actual)
- Shot count recommendations
- Spine weight tuning hints
- Stale graph detection
"""

from __future__ import annotations

from typing import Any

# Thresholds for triggering adjustments
DURATION_DEVIATION_THRESHOLD = 0.30  # 30% deviation triggers adjustment
STALE_GRAPH_HOURS = 24  # consider evidence stale if older than this


def _text(value: object) -> str:
    return str(value or "").strip()


def analyze_evidence(
    root: str | None = None, evidence: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Analyze narrative evidence and return planning adjustment suggestions.

    Args:
        root: Film root directory (reads narrative-evidence.json from there).
        evidence: Pre-loaded evidence dict (alternative to root).

    Returns:
        Dict with adjustment suggestions and summary metrics.
    """
    if evidence is None:
        from pathlib import Path

        from util import read_json

        evidence_path = Path(root or ".").expanduser() / "narrative-evidence.json"
        evidence = read_json(evidence_path) or {}

    items = evidence.get("items") or []
    if not items:
        return {"status": "no_data", "adjustments": [], "summary": {}}

    # Collect metrics
    total = len(items)
    verified = sum(1 for item in items if item.get("evidence_status") == "verified")
    missing = sum(1 for item in items if item.get("evidence_status") == "missing")
    uncertain = sum(1 for item in items if item.get("evidence_status") == "uncertain")

    adjustments: list[dict[str, Any]] = []

    # Per-item analysis: check duration deviations
    for item in items:
        evidence_id = _text(item.get("evidence_id"))
        status = _text(item.get("evidence_status"))
        executed = item.get("executed") or {}
        planned_duration = float(item.get("planned_duration") or 0)

        if status == "verified" and executed:
            actual_duration = float(executed.get("duration_sec") or 0)
            if planned_duration > 0 and actual_duration > 0:
                deviation = (actual_duration - planned_duration) / planned_duration
                if abs(deviation) > DURATION_DEVIATION_THRESHOLD:
                    direction = "over" if deviation > 0 else "under"
                    adjustments.append(
                        {
                            "evidence_id": evidence_id,
                            "type": "duration_deviation",
                            "direction": direction,
                            "planned_sec": planned_duration,
                            "actual_sec": actual_duration,
                            "deviation_pct": round(deviation * 100, 1),
                            "suggestion": (
                                f"Reduce planned duration for {evidence_id} "
                                f"by {abs(deviation) * 100:.0f}% (actual was {direction} planned)"
                            ),
                        }
                    )

    # Summary
    summary = {
        "total_items": total,
        "verified": verified,
        "missing": missing,
        "uncertain": uncertain,
        "verification_rate": round(verified / total, 2) if total > 0 else 0.0,
        "adjustments_count": len(adjustments),
    }

    return {
        "status": "ok" if adjustments else "no_adjustments_needed",
        "adjustments": adjustments,
        "summary": summary,
    }


def plan_adjustments_for_next_run(
    root: str | None = None,
    current_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate planning adjustments for the next run based on evidence.

    Returns a dict with:
    - beat_duration_adjustments: suggested weight changes per beat key
    - spine_recommendations: suggested spine changes
    - summary: overall assessment
    """
    analysis = analyze_evidence(root=root)
    if analysis.get("status") == "no_data":
        return {"status": "no_data", "message": "No narrative evidence available yet"}

    adjustments = analysis.get("adjustments") or []
    beat_adjustments: dict[str, dict[str, Any]] = {}

    for adj in adjustments:
        eid = adj.get("evidence_id", "")
        # Extract beat key from evidence_id (format: sceneId_btNN_key)
        parts = eid.split("_")
        if len(parts) >= 3:
            beat_key = parts[-1]
            if beat_key not in beat_adjustments:
                beat_adjustments[beat_key] = {
                    "deviations": [],
                    "suggested_weight_delta": 0.0,
                }
            beat_adjustments[beat_key]["deviations"].append(
                {
                    "evidence_id": eid,
                    "deviation_pct": adj.get("deviation_pct", 0),
                    "direction": adj.get("direction", "unknown"),
                }
            )
            # Accumulate weight delta suggestion
            delta = -adj["deviation_pct"] / 100 * 0.1  # gentle correction
            beat_adjustments[beat_key]["suggested_weight_delta"] += delta

    return {
        "status": "adjustments_available" if adjustments else "no_adjustments_needed",
        "beat_duration_adjustments": beat_adjustments,
        "summary": analysis.get("summary", {}),
        "message": (
            f"Found {len(adjustments)} duration deviations across {len(beat_adjustments)} beat keys"
        ),
    }
