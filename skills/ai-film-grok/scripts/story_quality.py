"""Story quality scoring — evaluates narrative completeness and coherence.

Provides a quality gate that can be used before locking the story graph.
Scores are heuristic-based (no LLM required) and cover:
- Hook strength
- Conflict clarity
- Arc completeness
- Payoff satisfaction
- Pacing balance
- Overall score
"""

from __future__ import annotations

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

# Scoring weights for each dimension.
DIMENSION_WEIGHTS = {
    "hook_strength": 0.15,
    "conflict_clarity": 0.20,
    "arc_completeness": 0.25,
    "payoff_satisfaction": 0.20,
    "pacing_balance": 0.10,
    "overall": 1.0,
}


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


def score_story(graph: dict[str, Any]) -> dict[str, Any]:
    """Score a story graph for narrative quality.

    Returns a dict with per-dimension scores and an overall score.
    """
    story = graph.get("story") if isinstance(graph.get("story"), dict) else {}

    scores = {
        "hook_strength": score_hook(story),
        "conflict_clarity": score_conflict(story),
        "arc_completeness": score_arc(story),
        "payoff_satisfaction": score_payoff(story),
        "pacing_balance": score_pacing(story),
    }

    # Overall = weighted average
    overall = sum(
        scores.get(dim, 0.0) * DIMENSION_WEIGHTS.get(dim, 0.0)
        for dim in (
            "hook_strength",
            "conflict_clarity",
            "arc_completeness",
            "payoff_satisfaction",
            "pacing_balance",
        )
    )
    scores["overall"] = round(overall, 2)

    return scores


def check_story_quality(graph: dict[str, Any], threshold: float = 0.4) -> dict[str, Any]:
    """Check story quality against a threshold.

    Returns {ok, scores, issues} where issues lists dimensions below threshold.
    """
    scores = score_story(graph)
    overall = scores.get("overall", 0.0)
    issues = [dim for dim, score in scores.items() if dim != "overall" and score < threshold]
    return {
        "ok": overall >= threshold and not issues,
        "scores": scores,
        "issues": issues,
        "threshold": threshold,
    }
