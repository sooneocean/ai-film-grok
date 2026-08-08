"""Story quality scoring — evaluates narrative completeness and coherence.

Provides a quality gate that can be used before locking the story graph.
Scores are heuristic-based (no LLM required) and cover:
- Hook strength
- Conflict clarity
- Arc completeness
- Payoff satisfaction
- Pacing balance
- Presentation-value (optional script-value-debrief dimensions)
- Overall score
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Required story fields for a complete narrative.
REQUIRED_STORY_FIELDS = (
    "protagonist_goal",
    "opposition",
    "stakes",
    "climax_choice",
    "ending_hook",
)

# Minimum emotional arc length for a complete arc.
MIN_ARC_LENGTH = 3

# Scoring weights for each dimension (core narrative; debrief dims optional overlay).
DIMENSION_WEIGHTS = {
    "hook_strength": 0.12,
    "conflict_clarity": 0.16,
    "arc_completeness": 0.18,
    "payoff_satisfaction": 0.14,
    "pacing_balance": 0.08,
    "promise_clarity": 0.10,
    "beat_value_coverage": 0.12,
    "setup_payoff_pair_count": 0.06,
    "dead_air_risk": 0.04,
    "overall": 1.0,
}

CORE_DIMENSIONS = (
    "hook_strength",
    "conflict_clarity",
    "arc_completeness",
    "payoff_satisfaction",
    "pacing_balance",
)

VALUE_DIMENSIONS = (
    "promise_clarity",
    "beat_value_coverage",
    "setup_payoff_pair_count",
    "dead_air_risk",
)


def _text(value: object) -> str:
    return str(value or "").strip()


def score_hook(story: dict[str, Any]) -> float:
    """Score hook strength (0.0–1.0)."""
    logline = _text(story.get("logline") or story.get("premise"))
    if not logline:
        return 0.0
    # A strong hook has a clear subject + conflict + stakes
    has_conflict = any(
        kw in logline for kw in ("冲突", "危险", "秘密", "对抗", "挑战", "危机", "争夺")
    )
    has_stakes = any(kw in logline for kw in ("代价", "后果", "失去", "危险", "命运", "决定"))
    score = 0.3  # base for having a logline
    if has_conflict:
        score += 0.35
    if has_stakes:
        score += 0.35
    return min(1.0, score)


def score_conflict(story: dict[str, Any]) -> float:
    """Score conflict clarity (0.0–1.0)."""
    opposition = _text(story.get("opposition"))
    stakes = _text(story.get("stakes"))
    score = 0.0
    if opposition:
        score += 0.5
    if stakes:
        score += 0.5
    return min(1.0, score)


def score_arc(story: dict[str, Any]) -> float:
    """Score emotional arc completeness (0.0–1.0)."""
    arc = story.get("emotional_arc") or []
    if not isinstance(arc, list):
        return 0.0
    length = len(arc)
    if length < MIN_ARC_LENGTH:
        return max(0.0, length / MIN_ARC_LENGTH)
    # Check for variety: at least 2 distinct emotional states
    unique = set(str(a) for a in arc)
    variety_bonus = min(0.3, len(unique) * 0.1)
    return min(1.0, 0.7 + variety_bonus)


def score_payoff(story: dict[str, Any]) -> float:
    """Score payoff satisfaction (0.0–1.0)."""
    climax = _text(story.get("climax_choice"))
    ending = _text(story.get("ending_hook"))
    score = 0.0
    if climax:
        score += 0.5
    if ending:
        score += 0.5
    return min(1.0, score)


def score_pacing(story: dict[str, Any]) -> float:
    """Score pacing balance (0.0–1.0)."""
    act = story.get("act_structure") or {}
    if not isinstance(act, dict):
        return 0.3
    setup = float(act.get("setup_ratio") or 0.0)
    confrontation = float(act.get("confrontation_ratio") or 0.0)
    resolution = float(act.get("resolution_ratio") or 0.0)
    total = setup + confrontation + resolution
    if total == 0:
        return 0.3
    # Ideal: setup ~20%, confrontation ~50%, resolution ~30%
    ideal = (0.20, 0.50, 0.30)
    actual = (setup / total, confrontation / total, resolution / total)
    deviation = sum(abs(a - i) for a, i in zip(actual, ideal, strict=True))
    # Lower deviation = better pacing
    return max(0.0, 1.0 - deviation * 2.0)


def _debrief_from_graph_or_root(
    graph: dict[str, Any],
    *,
    root: Path | str | None = None,
    debrief: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if isinstance(debrief, dict):
        return debrief
    embedded = graph.get("script_value_debrief")
    if isinstance(embedded, dict):
        return embedded
    if root is not None:
        try:
            from script_value_debrief import load_debrief

            return load_debrief(root)
        except Exception:  # noqa: BLE001
            return None
    return None


def score_value_dims(debrief: dict[str, Any] | None) -> dict[str, float]:
    """Presentation-value dimensions; neutral 0.5 when debrief absent (no hard punish)."""
    if not debrief:
        return {
            "promise_clarity": 0.5,
            "beat_value_coverage": 0.5,
            "setup_payoff_pair_count": 0.5,
            "dead_air_risk": 0.5,
            "debrief_present": 0.0,
        }
    try:
        from script_value_debrief import (
            score_beat_value_coverage,
            score_dead_air_awareness,
            score_promise_clarity,
            score_setup_payoff,
        )

        return {
            "promise_clarity": score_promise_clarity(debrief),
            "beat_value_coverage": score_beat_value_coverage(debrief),
            "setup_payoff_pair_count": score_setup_payoff(debrief),
            # Invert awareness: high awareness = low dead-air risk score channel name
            "dead_air_risk": score_dead_air_awareness(debrief),
            "debrief_present": 1.0,
        }
    except Exception:  # noqa: BLE001
        return {
            "promise_clarity": 0.5,
            "beat_value_coverage": 0.5,
            "setup_payoff_pair_count": 0.5,
            "dead_air_risk": 0.5,
            "debrief_present": 0.0,
        }


def score_story(
    graph: dict[str, Any],
    *,
    root: Path | str | None = None,
    debrief: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score a story graph for narrative quality.

    Returns a dict with per-dimension scores and an overall score.
    When a script-value-debrief is available, folds presentation-value dims into overall.
    """
    story = graph.get("story") if isinstance(graph.get("story"), dict) else {}

    scores: dict[str, Any] = {
        "hook_strength": score_hook(story),
        "conflict_clarity": score_conflict(story),
        "arc_completeness": score_arc(story),
        "payoff_satisfaction": score_payoff(story),
        "pacing_balance": score_pacing(story),
    }

    deb = _debrief_from_graph_or_root(graph, root=root, debrief=debrief)
    value = score_value_dims(deb)
    scores.update({k: value[k] for k in VALUE_DIMENSIONS})
    scores["debrief_present"] = value.get("debrief_present", 0.0)

    overall = sum(
        float(scores.get(dim, 0.0)) * float(DIMENSION_WEIGHTS.get(dim, 0.0))
        for dim in CORE_DIMENSIONS + VALUE_DIMENSIONS
    )
    scores["overall"] = round(overall, 2)

    return scores


def check_story_quality(
    graph: dict[str, Any],
    threshold: float = 0.4,
    *,
    root: Path | str | None = None,
    debrief: dict[str, Any] | None = None,
    require_debrief: bool = False,
) -> dict[str, Any]:
    """Check story quality against a threshold.

    Returns {ok, scores, issues} where issues lists dimensions below threshold.
    """
    scores = score_story(graph, root=root, debrief=debrief)
    overall = scores.get("overall", 0.0)
    issues = [
        dim
        for dim, score in scores.items()
        if dim not in {"overall", "debrief_present"}
        and isinstance(score, (int, float))
        and score < threshold
    ]
    # Neutral 0.5 value dims without debrief should not fail core quality
    if not scores.get("debrief_present"):
        issues = [i for i in issues if i not in VALUE_DIMENSIONS]
        if require_debrief:
            issues.append("debrief_missing")
    ok = overall >= threshold and not issues
    if require_debrief and not scores.get("debrief_present"):
        ok = False
    return {
        "ok": ok,
        "scores": scores,
        "issues": issues,
        "threshold": threshold,
        "require_debrief": require_debrief,
    }
