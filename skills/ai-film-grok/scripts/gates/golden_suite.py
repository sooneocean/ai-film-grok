#!/usr/bin/env python3
"""No-spend golden contract checks for the professional director workflow."""

from __future__ import annotations

import hashlib
from typing import Any


def _issue(code: str, message: str, *, ref: str | None = None) -> dict[str, Any]:
    return {"code": code, "message": message, "ref": ref}


def _overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return float(left.get("start") or 0) < float(right.get("end") or 0) and float(
        right.get("start") or 0
    ) < float(left.get("end") or 0)


def validate_golden_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Return advisory evidence; this function never authors a human approval."""
    issues: list[dict[str, Any]] = []
    fmt = contract.get("format") if isinstance(contract.get("format"), dict) else {}
    if fmt.get("aspect") != "9:16" or float(fmt.get("duration_sec") or 0) != 45:
        issues.append(_issue("GOLDEN_FORMAT_INVALID", "golden must be 45 seconds at 9:16"))

    characters = contract.get("characters") if isinstance(contract.get("characters"), dict) else {}
    shots = contract.get("shots") if isinstance(contract.get("shots"), list) else []
    wardrobe_rank: dict[tuple[str, str], int] = {}
    prop_rank: dict[tuple[str, str], int] = {}
    previous_axis: str | None = None
    delivered_dialogue: set[str] = set()

    for shot in shots:
        if not isinstance(shot, dict):
            continue
        shot_id = str(shot.get("id") or "shot")
        axis = str(shot.get("axis") or "")
        if previous_axis and axis and axis != previous_axis and not shot.get("axis_bridge"):
            issues.append(
                _issue("AXIS_CROSSING", "axis changed without a bridge shot", ref=shot_id)
            )
        if axis:
            previous_axis = axis

        appearances = shot.get("characters") if isinstance(shot.get("characters"), dict) else {}
        for character_id, appearance in appearances.items():
            master = (
                characters.get(character_id)
                if isinstance(characters.get(character_id), dict)
                else {}
            )
            appearance = appearance if isinstance(appearance, dict) else {}
            if appearance.get("face_hash") != master.get("face_hash"):
                issues.append(
                    _issue(
                        "FACE_DRIFT",
                        "face hash differs from cast master",
                        ref=f"{shot_id}:{character_id}",
                    )
                )
            hair = master.get("hair") if isinstance(master.get("hair"), dict) else {}
            if appearance.get("hair_color") != hair.get("color"):
                issues.append(
                    _issue(
                        "HAIR_COLOR_DRIFT",
                        "hair color differs from locked design",
                        ref=f"{shot_id}:{character_id}",
                    )
                )
            voice = master.get("voice") if isinstance(master.get("voice"), dict) else {}
            if appearance.get("voice_provider") != voice.get("provider") or appearance.get(
                "voice_id"
            ) != voice.get("voice_id"):
                issues.append(
                    _issue(
                        "VOICE_DRIFT",
                        "voice provider or voice id drifted",
                        ref=f"{shot_id}:{character_id}",
                    )
                )
            state = str(appearance.get("wardrobe_state") or "")
            ranks = (
                master.get("wardrobe_states")
                if isinstance(master.get("wardrobe_states"), dict)
                else {}
            )
            if state in ranks:
                key = (character_id, "wardrobe")
                rank = int(ranks[state])
                if key in wardrobe_rank and rank < wardrobe_rank[key]:
                    issues.append(
                        _issue(
                            "WARDROBE_REGRESSION",
                            "wardrobe state moved backward",
                            ref=f"{shot_id}:{character_id}",
                        )
                    )
                wardrobe_rank[key] = max(rank, wardrobe_rank.get(key, rank))

        props = shot.get("props") if isinstance(shot.get("props"), dict) else {}
        for prop_id, state in props.items():
            definition = (contract.get("props") or {}).get(prop_id, {})
            ranks = definition.get("states") if isinstance(definition, dict) else {}
            if state in ranks:
                key = (prop_id, "state")
                rank = int(ranks[state])
                if key in prop_rank and rank < prop_rank[key]:
                    issues.append(
                        _issue(
                            "PROP_STATE_REGRESSION",
                            "prop state moved backward",
                            ref=f"{shot_id}:{prop_id}",
                        )
                    )
                prop_rank[key] = max(rank, prop_rank.get(key, rank))

        dialogue_events = [
            item for item in shot.get("dialogue_events") or [] if isinstance(item, dict)
        ]
        delivered_dialogue.update(
            str(item.get("checksum")) for item in dialogue_events if item.get("checksum")
        )
        for cue in [item for item in shot.get("music_cues") or [] if isinstance(item, dict)]:
            if (
                any(_overlaps(cue, dialogue) for dialogue in dialogue_events)
                and float(cue.get("duck_db") or 0) < 6
            ):
                issues.append(
                    _issue("BGM_OVER_DIALOGUE", "music cue lacks dialogue ducking", ref=shot_id)
                )
        dialogue_by_id = {str(item.get("id")): item for item in dialogue_events}
        for caption in [
            item for item in shot.get("caption_events") or [] if isinstance(item, dict)
        ]:
            dialogue = dialogue_by_id.get(str(caption.get("dialogue_id")))
            inside_shot = float(shot.get("start") or 0) <= float(
                caption.get("start") or 0
            ) and float(caption.get("end") or 0) <= float(shot.get("end") or 0)
            inside_dialogue = bool(
                dialogue
                and float(dialogue.get("start") or 0) <= float(caption.get("start") or 0)
                and float(caption.get("end") or 0) <= float(dialogue.get("end") or 0)
            )
            if not inside_shot or not inside_dialogue:
                issues.append(
                    _issue(
                        "CAPTION_OUT_OF_WINDOW",
                        "caption exceeds shot or dialogue window",
                        ref=shot_id,
                    )
                )

    for dialogue_id, line in (contract.get("dialogue") or {}).items():
        if not isinstance(line, dict):
            continue
        expected_checksum = hashlib.sha256(str(line.get("text") or "").encode()).hexdigest()
        if line.get("checksum") != expected_checksum:
            issues.append(
                _issue(
                    "KEY_DIALOGUE_CHECKSUM_INVALID",
                    "declared key-dialogue checksum does not match its text",
                    ref=str(dialogue_id),
                )
            )
        if line.get("required") and expected_checksum not in delivered_dialogue:
            issues.append(
                _issue(
                    "KEY_DIALOGUE_MISSING",
                    "required dialogue checksum is absent",
                    ref=str(dialogue_id),
                )
            )

    current_human_approval = False
    for approval in contract.get("approvals") or []:
        if not isinstance(approval, dict):
            continue
        current = approval.get("input_hash") == approval.get("current_hash")
        human = approval.get("approver_type") in {"human", "user"}
        if not current:
            issues.append(
                _issue(
                    "APPROVAL_HASH_MISMATCH",
                    "approval is bound to a different input hash",
                    ref=str(approval.get("scope") or "approval"),
                )
            )
        current_human_approval = current_human_approval or bool(current and human)
    if not current_human_approval:
        issues.append(_issue("HUMAN_APPROVAL_MISSING", "a current human approval is required"))

    genre = str(contract.get("genre_pack") or "core")
    return {
        "ok": not issues,
        "kind": "professional-director-golden-report",
        "genre_pack": genre,
        "adult_rules_active": genre == "adult",
        "human_approval_required": True,
        "automated_result": "advisory",
        "issues": issues,
    }
