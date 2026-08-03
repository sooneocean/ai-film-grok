"""Execution feedback loop — derive planning adjustments from narrative evidence.

Reads narrative-evidence.json (planned vs executed) and produces
actionable adjustments for future planning runs:
- Beat duration adjustments (planned vs actual)
- Shot count recommendations
- Spine weight tuning hints
- Stale graph detection
- Pattern-based adjustment suggestions (e.g., consistent over/under for a genre)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC
from typing import Any

# Thresholds for triggering adjustments
DURATION_DEVIATION_THRESHOLD = 0.30  # 30% deviation triggers adjustment
SHOT_COUNT_DEVIATION_THRESHOLD = 0.25  # 25% deviation in shot count
STALE_GRAPH_HOURS = 24  # consider evidence stale if older than this
MIN_ADJUSTMENT_SAMPLES = 2  # minimum samples before suggesting weight change


def _text(value: object) -> str:
    return str(value or "").strip()


def _classify_deviation_pattern(
    deviations: list[dict[str, Any]],
) -> str:
    """Classify the overall pattern of deviations for a beat key.

    Returns one of: consistent_over, consistent_under, mixed, negligible.
    """
    if not deviations:
        return "negligible"
    directions = [d.get("direction") for d in deviations]
    over_count = directions.count("over")
    under_count = directions.count("under")
    total = len(directions)

    if over_count == total:
        return "consistent_over"
    if under_count == total:
        return "consistent_under"
    if over_count > 0 and under_count > 0:
        return "mixed"
    return "negligible"


def _compute_weight_suggestion(
    deviations: list[dict[str, Any]],
    pattern: str,
) -> dict[str, Any]:
    """Compute a suggested weight adjustment based on deviation pattern.

    Uses a weighted average of deviations, scaled more aggressively for
    consistent patterns and more gently for mixed ones.
    """
    if not deviations:
        return {"suggested_weight_delta": 0.0, "confidence": 0.0}

    abs_deviations = [abs(d.get("deviation_pct", 0)) for d in deviations]
    avg_abs_dev = sum(abs_deviations) / len(abs_deviations)

    # Pattern-based multiplier
    pattern_multiplier = {
        "consistent_over": 1.2,
        "consistent_under": 1.2,
        "mixed": 0.5,
        "negligible": 0.1,
    }.get(pattern, 0.5)

    # Confidence increases with sample count and deviation magnitude
    confidence = min(1.0, len(deviations) / 5.0 * (avg_abs_dev / 50.0))

    # Gentle correction: negative for over (reduce weight), positive for under (increase weight)
    net_direction = 0.0
    for d in deviations:
        dev = d.get("deviation_pct", 0)
        if d.get("direction") == "over":
            net_direction -= dev
        else:
            net_direction += dev
    net_direction /= len(deviations)

    suggested_delta = net_direction / 100 * 0.1 * pattern_multiplier

    return {
        "suggested_weight_delta": round(suggested_delta, 4),
        "confidence": round(confidence, 2),
        "avg_abs_deviation_pct": round(avg_abs_dev, 1),
        "pattern": pattern,
        "sample_count": len(deviations),
    }


def _analyze_shot_count(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Analyze shot count deviations from planned vs executed.

    Returns adjustments for beats where shot counts consistently differ.
    """
    adjustments: list[dict[str, Any]] = []
    shot_data: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item in items:
        evidence_id = _text(item.get("evidence_id"))
        executed = item.get("executed") or {}
        planned_shots = int(item.get("planned_shots") or 0)
        actual_shots = int(executed.get("shots_count") or 0)

        if planned_shots > 0 and actual_shots > 0:
            parts = evidence_id.split("_")
            if len(parts) >= 3:
                beat_key = parts[-1]
                shot_data[beat_key].append(
                    {
                        "evidence_id": evidence_id,
                        "planned": planned_shots,
                        "actual": actual_shots,
                        "deviation_pct": round(
                            (actual_shots - planned_shots) / planned_shots * 100, 1
                        ),
                    }
                )

    for beat_key, data in shot_data.items():
        if len(data) < MIN_ADJUSTMENT_SAMPLES:
            continue
        avg_dev = sum(d["deviation_pct"] for d in data) / len(data)
        if abs(avg_dev) > SHOT_COUNT_DEVIATION_THRESHOLD * 100:
            direction = "over" if avg_dev > 0 else "under"
            adjustments.append(
                {
                    "beat_key": beat_key,
                    "type": "shot_count_deviation",
                    "direction": direction,
                    "planned_shots": data[0]["planned"],
                    "avg_actual_shots": round(
                        sum(d["actual"] for d in data) / len(data), 1
                    ),
                    "avg_deviation_pct": round(avg_dev, 1),
                    "suggestion": (
                        f"Adjust shots_n for beat '{beat_key}': "
                        f"planned {data[0]['planned']}, actual avg {round(sum(d['actual'] for d in data) / len(data), 1)}"
                    ),
                }
            )

    return adjustments


def _detect_stale_evidence(
    items: list[dict[str, Any]],
    stale_hours: float = STALE_GRAPH_HOURS,
) -> list[dict[str, Any]]:
    """Detect evidence items that are older than the stale threshold.

    Returns items that may need re-verification.
    """
    from datetime import datetime

    stale_items: list[dict[str, Any]] = []
    now = datetime.now(UTC)

    for item in items:
        timestamp = item.get("timestamp") or item.get("recorded_at")
        if not timestamp:
            continue
        try:
            if isinstance(timestamp, str):
                ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            else:
                ts = timestamp
            age = (now - ts).total_seconds() / 3600
            if age > stale_hours:
                stale_items.append(
                    {
                        "evidence_id": _text(item.get("evidence_id")),
                        "age_hours": round(age, 1),
                        "suggestion": "Consider re-verifying this evidence item",
                    }
                )
        except (ValueError, TypeError):
            continue

    return stale_items


def _generate_genre_adjustments(
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate genre-level adjustment suggestions based on evidence patterns.

    Groups evidence by genre (extracted from evidence_id or metadata)
    and suggests spine/weight adjustments for genres with systematic deviations.
    """
    genre_data: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item in items:
        evidence_id = _text(item.get("evidence_id"))
        genre = item.get("genre") or "adult"
        executed = item.get("executed") or {}
        planned_duration = float(item.get("planned_duration") or 0)
        actual_duration = float(executed.get("duration_sec") or 0)

        if planned_duration > 0 and actual_duration > 0:
            deviation = (actual_duration - planned_duration) / planned_duration
            genre_data[genre].append(
                {
                    "evidence_id": evidence_id,
                    "deviation_pct": round(deviation * 100, 1),
                    "direction": "over" if deviation > 0 else "under",
                }
            )

    adjustments: list[dict[str, Any]] = []
    for genre, deviations in genre_data.items():
        if len(deviations) < MIN_ADJUSTMENT_SAMPLES:
            continue
        avg_dev = sum(d["deviation_pct"] for d in deviations) / len(deviations)
        if abs(avg_dev) > DURATION_DEVIATION_THRESHOLD * 100:
            pattern = _classify_deviation_pattern(deviations)
            weight_suggestion = _compute_weight_suggestion(deviations, pattern)
            adjustments.append(
                {
                    "genre": genre,
                    "type": "genre_duration_pattern",
                    "avg_deviation_pct": round(avg_dev, 1),
                    "pattern": pattern,
                    "weight_suggestion": weight_suggestion,
                    "suggestion": (
                        f"Genre '{genre}' shows {pattern} duration deviation "
                        f"({avg_dev:+.1f}%). Consider adjusting spine weights "
                        f"for this genre (confidence: {weight_suggestion['confidence']:.0%})"
                    ),
                }
            )

    return adjustments


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

    # Shot count analysis
    shot_adjustments = _analyze_shot_count(items)
    adjustments.extend(shot_adjustments)

    # Stale evidence detection
    stale_items = _detect_stale_evidence(items)

    # Genre-level pattern analysis
    genre_adjustments = _generate_genre_adjustments(items)

    # Beat-level weight suggestions (enhanced with pattern classification)
    beat_deviations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for adj in adjustments:
        if adj.get("type") == "duration_deviation":
            eid = adj.get("evidence_id", "")
            parts = eid.split("_")
            if len(parts) >= 3:
                beat_key = parts[-1]
                beat_deviations[beat_key].append(
                    {
                        "evidence_id": eid,
                        "deviation_pct": adj.get("deviation_pct", 0),
                        "direction": adj.get("direction", "unknown"),
                    }
                )

    beat_weight_suggestions: dict[str, dict[str, Any]] = {}
    for beat_key, deviations in beat_deviations.items():
        if len(deviations) >= MIN_ADJUSTMENT_SAMPLES:
            pattern = _classify_deviation_pattern(deviations)
            suggestion = _compute_weight_suggestion(deviations, pattern)
            suggestion["beat_key"] = beat_key
            suggestion["type"] = "beat_weight_adjustment"
            beat_weight_suggestions[beat_key] = suggestion

    # Summary
    summary = {
        "total_items": total,
        "verified": verified,
        "missing": missing,
        "uncertain": uncertain,
        "verification_rate": round(verified / total, 2) if total > 0 else 0.0,
        "duration_adjustments": len(
            [a for a in adjustments if a.get("type") == "duration_deviation"]
        ),
        "shot_count_adjustments": len(shot_adjustments),
        "genre_adjustments": len(genre_adjustments),
        "beat_weight_suggestions": len(beat_weight_suggestions),
        "stale_items": len(stale_items),
    }

    return {
        "status": "ok" if adjustments else "no_adjustments_needed",
        "adjustments": adjustments,
        "beat_weight_suggestions": beat_weight_suggestions,
        "genre_adjustments": genre_adjustments,
        "stale_evidence": stale_items,
        "summary": summary,
    }


def plan_adjustments_for_next_run(
    root: str | None = None,
    current_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate planning adjustments for the next run based on evidence.

    Returns a dict with:
    - beat_duration_adjustments: suggested weight changes per beat key
    - shot_count_recommendations: suggested shot count changes
    - genre_spine_hints: spine weight tuning by genre
    - stale_detection: evidence items needing re-verification
    - summary: overall assessment
    """
    analysis = analyze_evidence(root=root)
    if analysis.get("status") == "no_data":
        return {"status": "no_data", "message": "No narrative evidence available yet"}

    adjustments = analysis.get("adjustments") or []
    beat_adjustments: dict[str, dict[str, Any]] = {}

    for adj in adjustments:
        eid = adj.get("evidence_id", "")
        parts = eid.split("_")
        if len(parts) >= 3:
            beat_key = parts[-1]
            if beat_key not in beat_adjustments:
                beat_adjustments[beat_key] = {
                    "deviations": [],
                    "suggested_weight_delta": 0.0,
                    "confidence": 0.0,
                }
            beat_adjustments[beat_key]["deviations"].append(
                {
                    "evidence_id": eid,
                    "deviation_pct": adj.get("deviation_pct", 0),
                    "direction": adj.get("direction", "unknown"),
                }
            )
            delta = -adj["deviation_pct"] / 100 * 0.1
            beat_adjustments[beat_key]["suggested_weight_delta"] += delta

    # Apply beat weight suggestions from pattern analysis
    for beat_key, suggestion in analysis.get("beat_weight_suggestions", {}).items():
        if beat_key not in beat_adjustments:
            beat_adjustments[beat_key] = {
                "deviations": [],
                "suggested_weight_delta": 0.0,
                "confidence": 0.0,
            }
        beat_adjustments[beat_key]["suggested_weight_delta"] = suggestion.get(
            "suggested_weight_delta", 0.0
        )
        beat_adjustments[beat_key]["confidence"] = suggestion.get("confidence", 0.0)
        beat_adjustments[beat_key]["pattern"] = suggestion.get("pattern", "negligible")

    # Build genre-level recommendations
    genre_recommendations: dict[str, dict[str, Any]] = {}
    for ga in analysis.get("genre_adjustments", []):
        genre = ga.get("genre", "")
        genre_recommendations[genre] = {
            "pattern": ga.get("pattern", "negligible"),
            "avg_deviation_pct": ga.get("avg_deviation_pct", 0),
            "weight_suggestion": ga.get("weight_suggestion", {}),
        }

    return {
        "status": "adjustments_available" if adjustments else "no_adjustments_needed",
        "beat_duration_adjustments": beat_adjustments,
        "shot_count_recommendations": [
            a for a in adjustments if a.get("type") == "shot_count_deviation"
        ],
        "genre_spine_hints": genre_recommendations,
        "stale_evidence": analysis.get("stale_evidence", []),
        "summary": {
            **analysis.get("summary", {}),
            "message": (
                f"Found {len(adjustments)} duration deviations across "
                f"{len(beat_adjustments)} beat keys, "
                f"{len(genre_recommendations)} genre patterns"
            ),
        },
    }
