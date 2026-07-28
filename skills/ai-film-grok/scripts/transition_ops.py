"""Per-join transition operations shared by planning, post, and delivery receipts.

A hard cut is still an editorial operation.  Materialising every seam prevents
the post layer from treating an unplanned join as a safe place for decoration.
"""

from __future__ import annotations

from typing import Any

from edit_policy import craft_to_intent_style, normalize_edit_craft


class TransitionOperationError(ValueError):
    pass


_CONTINUE_MODES = frozenset({"continue", "match", "match_cut", "byte"})
_MID_ACTION_CUTS = frozenset({"action", "mid_action", "mid-action", "mid_motion"})


def _chain_mode(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return str(dsl.get("chain_mode") or "").strip().lower()


def _cut_on(shot: dict[str, Any]) -> str:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    return str(dsl.get("cut_on") or "").strip().lower()


def _audio_mode(craft: str, intent: str) -> str:
    if craft in {"soft_glue", "scene_bridge", "mood_hold"}:
        return "L_cut"
    if craft == "whip_soft":
        return "J_cut"
    return "cut" if intent == "hard" else "acrossfade"


def build_transition_operations(
    shots: list[dict[str, Any]],
    *,
    crafts: list[str],
    intents: list[str],
    styles: list[str],
    durations: list[float],
    authored: list[object] | None = None,
) -> list[dict[str, Any]]:
    """Return one validated operation for each shot seam.

    Author entries may add ``reason`` or set ``locked`` but cannot weaken the
    continue-chain hard-cut safety contract.
    """
    expected = max(0, len(shots) - 1)
    for name, values in (
        ("edit_craft", crafts),
        ("transition_intents", intents),
        ("transition_styles", styles),
        ("join_transition_secs", durations),
    ):
        if len(values) != expected:
            raise TransitionOperationError(
                f"{name} length must be n_shots-1={expected}; got {len(values)}"
            )
    if authored is not None and len(authored) != expected:
        raise TransitionOperationError(
            f"transition_ops length must be n_shots-1={expected}; got {len(authored)}"
        )

    operations: list[dict[str, Any]] = []
    for index in range(expected):
        prev, nxt = shots[index], shots[index + 1]
        craft = normalize_edit_craft(crafts[index], field=f"edit_craft[{index}]")
        derived_intent, _ = craft_to_intent_style(craft)
        intent = str(intents[index]).strip().lower()
        if intent not in {"hard", "soft", "hold"}:
            raise TransitionOperationError(f"transition_intents[{index}] must be hard|soft|hold")
        continue_join = _chain_mode(nxt) in _CONTINUE_MODES
        if continue_join:
            intent = "hard"
            craft = "cut_on_action" if _cut_on(nxt) in _MID_ACTION_CUTS else "match_cut"
            derived_intent = "hard"
        if derived_intent != intent and not continue_join:
            # The persisted intent is the renderer contract; craft remains the
            # editorial label when an author deliberately overrides it.
            pass
        try:
            duration = max(0.0, min(0.8, float(durations[index])))
        except (TypeError, ValueError) as exc:
            raise TransitionOperationError(
                f"join_transition_secs[{index}] must be numeric"
            ) from exc
        if continue_join:
            duration = 0.0

        op: dict[str, Any] = {
            "join_id": f"{prev.get('id')}__{nxt.get('id')}",
            "join_index": index,
            "from_shot": str(prev.get("id") or ""),
            "to_shot": str(nxt.get("id") or ""),
            "type": craft,
            "purpose": "action_continuity" if continue_join else "editorial_rhythm",
            "continuity_class": "continue" if continue_join else "cut",
            "picture": {
                "base": "hard_cut" if intent == "hard" else "xfade",
                "style": "none" if intent == "hard" else str(styles[index]),
                "duration_sec": round(duration, 3),
                # HyperFrames may decorate only a non-continuity scene/cut seam.
                "hyperframes_overlay": "none",
            },
            "audio": {"mode": _audio_mode(craft, intent), "duration_sec": round(duration, 3)},
            "anchors": {
                "cut_on": _cut_on(nxt) or None,
                "from_action": str(prev.get("action") or "") or None,
                "to_action": str(nxt.get("action") or "") or None,
            },
            "qa": {
                "must_not": ["double_image", "subtitle_collision"],
                "review_frames": [-6, -2, 0, 2, 6],
            },
        }
        if authored is not None:
            supplied = authored[index]
            if not isinstance(supplied, dict):
                raise TransitionOperationError(f"transition_ops[{index}] must be an object")
            if "locked" in supplied:
                if not isinstance(supplied["locked"], bool):
                    raise TransitionOperationError(
                        f"transition_ops[{index}].locked must be boolean"
                    )
                if supplied["locked"]:
                    op["locked"] = True
            if "reason" in supplied:
                if not isinstance(supplied["reason"], str):
                    raise TransitionOperationError(
                        f"transition_ops[{index}].reason must be a string"
                    )
                if supplied["reason"].strip():
                    op["reason"] = supplied["reason"].strip()
        operations.append(op)
    return operations


def assert_hyperframes_safe_operations(operations: object) -> None:
    """Block a designed-post package from decorating byte-continuity joins."""
    if not isinstance(operations, list):
        raise TransitionOperationError("transition_ops must be an array")
    for index, op in enumerate(operations):
        if not isinstance(op, dict):
            raise TransitionOperationError(f"transition_ops[{index}] must be an object")
        if op.get("continuity_class") != "continue":
            continue
        picture = op.get("picture")
        if not isinstance(picture, dict):
            raise TransitionOperationError(f"transition_ops[{index}].picture must be an object")
        if (
            picture.get("base") != "hard_cut"
            or float(picture.get("duration_sec") or 0) != 0.0
            or picture.get("hyperframes_overlay") != "none"
        ):
            raise TransitionOperationError(
                f"transition_ops[{index}] continue seam must be hard_cut, zero-duration, and no HyperFrames overlay"
            )
