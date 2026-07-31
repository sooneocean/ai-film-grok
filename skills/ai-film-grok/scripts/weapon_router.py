#!/usr/bin/env python3
"""Project workflow demand onto a verified local weapon without performing I/O."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from comfy_armory import ComfyArmoryError, load_armory, select_weapon
from util import read_json

_STILL_DEMAND_STAGES = frozenset(
    {
        "department_look_lock",
        "shot_animatic_lock",
        "pilot_approval",
    }
)
_STILL_PROVIDER_KEYS = ("still_provider",)
_I2V_PROVIDER_KEYS = ("i2v_provider", "video_provider")
_EDIT_OPERATIONS = frozenset(
    {
        "image-edit",
        "image_edit",
        "local-image-edit",
        "wardrobe-edit",
        "color-edit",
        "identity-preserving-edit",
    }
)


def _locked_provider(
    root: Path,
    keys: tuple[str, ...],
    *,
    selected_local_provider: str | None = None,
) -> str | None:
    spec = read_json(root / "film-spec.json") or {}
    for key in keys:
        value = str(spec.get(key) or "").strip()
        if value and value not in {
            "auto",
            "default",
            "unlocked",
            selected_local_provider,
        }:
            return value
    return None


def _requested_operation(*items: dict[str, Any] | None) -> str | None:
    for item in items:
        if not isinstance(item, dict):
            continue
        nested = item.get("input")
        values = (
            item.get("operation"),
            item.get("intent"),
            nested.get("operation") if isinstance(nested, dict) else None,
            nested.get("intent") if isinstance(nested, dict) else None,
        )
        for value in values:
            normalized = str(value or "").strip().lower()
            if normalized:
                return normalized
    return None


def _research_intents() -> set[str]:
    """Return research-only intents which must never fall back to production."""
    return {
        str(intent).strip().lower()
        for weapon in load_armory().get("research_weapons", [])
        if isinstance(weapon, dict)
        for intent in weapon.get("intents", [])
        if str(intent).strip()
    }


def build_weapon_route(
    root: Path | str,
    *,
    workflow: dict[str, Any],
    primary_job: dict[str, Any] | None = None,
    primary_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic dispatch projection for an unlocked visual demand."""
    base = Path(root).expanduser().resolve()
    stage = str(workflow.get("current_stage") or "")
    job_skill = str((primary_job or {}).get("skillId") or "")
    action_id = str((primary_action or {}).get("id") or "")
    still_demand = bool(
        stage in _STILL_DEMAND_STAGES
        or job_skill == "keyframe.generate"
        or action_id == "state-index-plan"
    )
    motion_demand = bool(
        stage == "bulk" or job_skill == "image.animate" or action_id == "grok-i2v-bulk"
    )
    requested_operation = _requested_operation(primary_job, primary_action)
    edit_demand = still_demand and requested_operation in _EDIT_OPERATIONS
    demand_detected = still_demand or motion_demand
    common = {
        "schema_version": 1,
        "kind": "ai-film-weapon-route",
        "workflow_stage": stage or None,
        "demand_detected": demand_detected,
        "auto_select": False,
        "auto_execute_when_requested": False,
        "advance_eligible": False,
        "requires_live_probe": False,
    }
    if not demand_detected:
        return {**common, "status": "not_required", "reason": "no current visual weapon demand"}

    try:
        research_intents = _research_intents()
    except ComfyArmoryError as exc:
        return {
            **common,
            "status": "blocked",
            "reason": f"cannot verify research-only intent boundary: {exc}",
            "fail_closed": True,
        }
    if requested_operation in research_intents:
        return {
            **common,
            "status": "blocked",
            "operation": requested_operation,
            "reason": "research-only intent cannot be routed or auto-executed",
            "fail_closed": True,
        }

    provider_keys = _I2V_PROVIDER_KEYS if motion_demand else _STILL_PROVIDER_KEYS
    locked_provider = _locked_provider(
        base,
        provider_keys,
        selected_local_provider="comfy_lan" if still_demand else None,
    )
    if locked_provider:
        return {
            **common,
            "status": "provider_locked",
            "provider": locked_provider,
            "reason": "the film already locks a still provider; the armory cannot switch it",
        }

    spec = read_json(base / "film-spec.json") or {}
    adult = str(spec.get("genre") or "").strip().lower() == "adult"
    operation = (
        ("adult-meat-motion-i2v" if adult else "image-to-video")
        if motion_demand
        else "local-image-edit"
        if edit_demand
        else "text-to-image"
    )
    production_stage = "pilot" if stage == "pilot_approval" else "production"
    try:
        route = select_weapon(
            operation,
            stage=production_stage,
            identity_lock=edit_demand,
        )
    except ComfyArmoryError as exc:
        return {
            **common,
            "status": "blocked",
            "reason": str(exc),
            "fail_closed": True,
        }
    weapon = route["weapon"]
    return {
        **common,
        "status": "ready",
        "operation": route.get("operation") or route.get("intent") or operation,
        "quality": route.get("quality") or "max_practical",
        "weapon_id": weapon["id"],
        "provider": str(weapon.get("provider") or "comfy_lan"),
        "command": f"aifilm comfy route --intent {operation}",
        "auto_select": True,
        "auto_execute_when_requested": True,
        "requires_live_probe": True,
        "pilot_verified": bool((weapon.get("verified") or {}).get("real_pilot")),
        "reason": (
            "unlocked visual demand maps to the highest-priority pilot-verified local weapon; "
            "the execution command performs current model read-back"
        ),
    }
