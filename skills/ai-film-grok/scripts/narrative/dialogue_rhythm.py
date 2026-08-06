"""Dialogue rhythm analysis and pacing guidance."""

from __future__ import annotations

from typing import Any

# Pacing rules per dramatic_function
RHYTHM_RULES: dict[str, dict[str, Any]] = {
    "hook": {
        "min_turns": 1,
        "max_turns": 3,
        "max_total_sec": 15.0,
        "description": "短促有力，1-3 句收住",
    },
    "approach": {
        "min_turns": 2,
        "max_turns": 6,
        "max_total_sec": 30.0,
        "description": "来回推挤，2-6 句建立张力",
    },
    "sensory": {
        "min_turns": 1,
        "max_turns": 4,
        "max_total_sec": 20.0,
        "description": "感官沉浸，1-4 句放慢节奏",
    },
    "reaction": {
        "min_turns": 1,
        "max_turns": 3,
        "max_total_sec": 15.0,
        "description": "反应要快，1-3 句",
    },
    "action": {
        "min_turns": 1,
        "max_turns": 4,
        "max_total_sec": 25.0,
        "description": "动作驱动，1-4 句加速",
    },
    "afterglow": {
        "min_turns": 1,
        "max_turns": 2,
        "max_total_sec": 10.0,
        "description": "余韵简短，1-2 句",
    },
}

# Consecutive same-speaker threshold before warning
MAX_CONSECUTIVE_SAME_SPEAKER = 3


def analyze_dialogue_rhythm(scene: dict[str, Any]) -> dict[str, Any]:
    """Analyze the rhythm of dialogue turns in a scene."""
    turns = scene.get("dialogue_turns") or []
    if not isinstance(turns, list):
        return {"status": "ok", "turn_count": 0}

    turn_count = len(turns)
    if turn_count == 0:
        return {"status": "ok", "turn_count": 0}

    total_sec = sum(
        max(0.0, float(t.get("duration_sec") or 0)) for t in turns if isinstance(t, dict)
    )

    issues: list[str] = []

    # Consecutive same-speaker check
    same_speaker_streak = 0
    prev_speaker = ""
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        speaker = _text(turn.get("speaker"))
        if speaker == prev_speaker:
            same_speaker_streak += 1
            if same_speaker_streak > MAX_CONSECUTIVE_SAME_SPEAKER:
                issues.append(
                    f"角色「{speaker}」连续 {same_speaker_streak + 1} 句无打断 — "
                    "建议插入对方反应或动作插入"
                )
        else:
            same_speaker_streak = 0
        prev_speaker = speaker

    # Dramatic function pacing check
    df = _scene_dramatic_function(scene)
    rules = RHYTHM_RULES.get(df, RHYTHM_RULES["approach"])

    if turn_count > rules["max_turns"]:
        issues.append(
            f"场景 {_text(scene.get('scene_id'))}: "
            f"{turn_count} 句对白超过 {df} 的建议上限 {rules['max_turns']} 句 — "
            "建议精简或拆分为两个场景"
        )

    if total_sec > rules["max_total_sec"]:
        issues.append(
            f"场景总时长 {total_sec:.1f}s 超过 {df} 的建议上限 {rules['max_total_sec']}s — "
            "建议精简或拆分为两个场景"
        )

    return {
        "status": "issues_found" if issues else "ok",
        "turn_count": turn_count,
        "total_sec": round(total_sec, 1),
        "avg_sec_per_turn": round(total_sec / turn_count, 1) if turn_count else 0.0,
        "dramatic_function": df,
        "rhythm_rules": rules,
        "issues": issues,
    }


def _scene_dramatic_function(scene: dict[str, Any]) -> str:
    """Infer dramatic function from scene's dramatic_purpose or coverage_intent."""
    purpose = _text(scene.get("dramatic_purpose")) or "advance story"
    purpose_lower = purpose.lower()

    if "hook" in purpose_lower or "opening" in purpose_lower:
        return "hook"
    if "approach" in purpose_lower or "advance" in purpose_lower:
        return "approach"
    if "sensory" in purpose_lower or "atmosphere" in purpose_lower:
        return "sensory"
    if "reaction" in purpose_lower or "response" in purpose_lower:
        return "reaction"
    if "action" in purpose_lower or "climax" in purpose_lower or "peak" in purpose_lower:
        return "action"
    if "afterglow" in purpose_lower or "ending" in purpose_lower or "closure" in purpose_lower:
        return "afterglow"

    # Fallback: check coverage_intent for clues
    coverage = scene.get("coverage_intent")
    if isinstance(coverage, dict):
        if coverage.get("shot_reverse_shot"):
            return "approach"
        if coverage.get("action_cover"):
            return "action"

    return "approach"


def _text(value: object) -> str:
    return str(value or "").strip()
