"""Strict, pixel-backed wardrobe-state ladders.

This module deliberately plans and registers state photos locally.  It never
calls an image provider: each I2I step needs an explicit human-approved output
before it can become the input for the following step.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from util import utc_now


def _slug(value: object) -> str:
    text = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or ""))
    return "-".join(part for part in text.split("-") if part) or "garment"


def _sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def needs_ladder(states: set[str]) -> bool:
    return any(state not in {"", "default", "full", "armored"} for state in states)


def exact_state_id(shot: dict[str, Any]) -> str | None:
    dsl = shot.get("dsl") if isinstance(shot.get("dsl"), dict) else {}
    value = shot.get("wardrobe_state_id") or dsl.get("wardrobe_state_id")
    return str(value).strip() if value else None


def _states(ladder: dict[str, Any]) -> list[dict[str, Any]]:
    states = ladder.get("states") if isinstance(ladder.get("states"), list) else []
    return [state for state in states if isinstance(state, dict) and state.get("id")]


def state_for_id(bible: dict[str, Any], character_id: str, state_id: str) -> dict[str, Any] | None:
    ladders = (
        bible.get("wardrobe_ladders") if isinstance(bible.get("wardrobe_ladders"), dict) else {}
    )
    for key in (character_id, "hero"):
        ladder = ladders.get(key)
        if not isinstance(ladder, dict):
            continue
        for state in _states(ladder):
            if str(state.get("id")) == state_id:
                return state
    return None


def resolve_exact_state_photo(
    bible: dict[str, Any], character_id: str, state_id: str, *, root: Path | None = None
) -> str | None:
    state = state_for_id(bible, character_id, state_id)
    if not state or state.get("status") != "approved" or not state.get("path"):
        return None
    path = Path(str(state["path"]))
    if root is not None and not path.is_absolute():
        path = root / path
    if root is not None and not path.is_file():
        return None
    return str(state["path"])


def resolve_state_photo_for_category(
    bible: dict[str, Any], character_id: str, wardrobe_state: str, *, root: Path | None = None
) -> str | None:
    """Return the deepest approved exact state tagged with a legacy category."""
    ladders = (
        bible.get("wardrobe_ladders") if isinstance(bible.get("wardrobe_ladders"), dict) else {}
    )
    wanted = str(wardrobe_state or "full").strip().lower()
    for key in (character_id, "hero"):
        ladder = ladders.get(key)
        if not isinstance(ladder, dict):
            continue
        matches = [
            state
            for state in _states(ladder)
            if str(state.get("wardrobe_state") or "").lower() == wanted
            and state.get("status") == "approved"
            and state.get("path")
        ]
        if matches:
            return resolve_exact_state_photo(bible, key, str(matches[-1]["id"]), root=root)
    return None


def ensure_ladder(
    bible: dict[str, Any], character_id: str, states_used: set[str], *, root: Path
) -> dict[str, Any] | None:
    """Create only an editable skeleton; never guess a garment inventory."""
    if not needs_ladder(states_used):
        return None
    ladders = bible.setdefault("wardrobe_ladders", {})
    if not isinstance(ladders, dict):
        ladders = {}
        bible["wardrobe_ladders"] = ladders
    ladder = ladders.get(character_id)
    if not isinstance(ladder, dict):
        ladder = {
            "status": "needs_wardrobe_breakdown",
            "garments": [],
            "states": [],
            "note": "List every removable garment outer-to-inner before state I2I generation.",
        }
        ladders[character_id] = ladder
    garments = ladder.get("garments") if isinstance(ladder.get("garments"), list) else []
    states = _states(ladder)
    if garments and not states:
        garment_ids = [
            str(item.get("id") or _slug(item.get("label")))
            if isinstance(item, dict)
            else _slug(item)
            for item in garments
        ]
        peak = (
            "bare"
            if "bare" in states_used
            else "undressed"
            if "undressed" in states_used
            else "partial"
        )
        cast_masters = (
            bible.get("cast_masters") if isinstance(bible.get("cast_masters"), dict) else {}
        )
        full_path = (
            cast_masters.get(character_id)
            or cast_masters.get("hero")
            or f"canonical/cast-states/{character_id}/full.png"
        )
        generated: list[dict[str, Any]] = [
            {
                "id": "full",
                "parent_state_id": None,
                "removed_garment_ids": [],
                "wardrobe_state": "full",
                "path": str(full_path),
                "status": "pending",
            }
        ]
        for index, garment_id in enumerate(garment_ids, start=1):
            state_id = f"remove-{_slug(garment_id)}"
            generated.append(
                {
                    "id": state_id,
                    "parent_state_id": generated[-1]["id"],
                    "removed_garment_ids": garment_ids[:index],
                    "wardrobe_state": peak if index == len(garment_ids) else "partial",
                    "path": f"canonical/cast-states/{character_id}/{state_id}.png",
                    "status": "pending",
                }
            )
        ladder["states"] = generated
        ladder["status"] = "pending_approval"
    return ladder


def ladder_plan(
    bible: dict[str, Any], character_id: str, *, root: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (hard issues, serial I2I plan) for a character ladder."""
    ladders = (
        bible.get("wardrobe_ladders") if isinstance(bible.get("wardrobe_ladders"), dict) else {}
    )
    ladder = ladders.get(character_id)
    if not isinstance(ladder, dict):
        return ([{"code": "MISSING_WARDROBE_LADDER", "character_id": character_id}], [])
    garments = ladder.get("garments") if isinstance(ladder.get("garments"), list) else []
    garment_ids = [
        str(item.get("id") or _slug(item.get("label"))) if isinstance(item, dict) else _slug(item)
        for item in garments
    ]
    if not garment_ids:
        return ([{"code": "NEEDS_WARDROBE_BREAKDOWN", "character_id": character_id}], [])
    states = _states(ladder)
    if len(states) != len(garment_ids) + 1 or not states or str(states[0].get("id")) != "full":
        return ([{"code": "WARDROBE_LADDER_STATES_INCOMPLETE", "character_id": character_id}], [])
    hard: list[dict[str, Any]] = []
    plan: list[dict[str, Any]] = []
    for index, state in enumerate(states):
        sid = str(state["id"])
        expected_parent = None if index == 0 else str(states[index - 1]["id"])
        if state.get("parent_state_id") != expected_parent:
            hard.append(
                {
                    "code": "WARDROBE_LADDER_PARENT_MISMATCH",
                    "character_id": character_id,
                    "state_id": sid,
                }
            )
        expected_removed = garment_ids[:index]
        if list(state.get("removed_garment_ids") or []) != expected_removed:
            hard.append(
                {
                    "code": "WARDROBE_LADDER_STEP_INVALID",
                    "character_id": character_id,
                    "state_id": sid,
                }
            )
        path_value = state.get("path") or f"canonical/cast-states/{character_id}/{sid}.png"
        state.setdefault("path", path_value)
        path = Path(str(path_value))
        if not path.is_absolute():
            path = root / path
        approved = state.get("status") == "approved" and path.is_file()
        if approved and state.get("sha256") != _sha256(path):
            hard.append(
                {"code": "WARDROBE_STATE_HASH_DRIFT", "character_id": character_id, "state_id": sid}
            )
        if index == 0:
            if not approved:
                hard.append(
                    {
                        "code": "WARDROBE_FULL_STATE_UNAPPROVED",
                        "character_id": character_id,
                        "state_id": sid,
                    }
                )
        elif not approved:
            plan.append(
                {
                    "action": "generate_wardrobe_state_photo",
                    "character_id": character_id,
                    "wardrobe_state_id": sid,
                    "parent_state_id": expected_parent,
                    "remove_garment_id": garment_ids[index - 1],
                    "out": str(path_value),
                    "requires": "previous state approved; image_edit only from parent state photo",
                    "agent_hint": f"image_edit the approved {expected_parent} state; remove only {garment_ids[index - 1]}; save {path_value}; then aifilm state-index approve-state",
                }
            )
    return hard, plan


def approve_state(
    bible: dict[str, Any], character_id: str, state_id: str, image: Path, *, root: Path
) -> dict[str, Any]:
    state = state_for_id(bible, character_id, state_id)
    if not state:
        raise ValueError(f"unknown wardrobe state {character_id}:{state_id}")
    image = image.expanduser().resolve()
    if not image.is_file():
        raise ValueError(f"state image does not exist: {image}")
    parent_id = state.get("parent_state_id")
    if parent_id:
        parent = state_for_id(bible, character_id, str(parent_id))
        if not parent or parent.get("status") != "approved":
            raise ValueError(f"parent state {parent_id} must be approved first")
    try:
        stored = str(image.relative_to(root))
    except ValueError:
        stored = str(image)
    state.update(
        {"path": stored, "sha256": _sha256(image), "status": "approved", "approved_at": utc_now()}
    )
    return state
