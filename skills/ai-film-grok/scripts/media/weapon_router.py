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
        # R5: weapon layer (local armory + provider lock); not capability rank
        "layer": "weapon",
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
        selected_local_provider="comfy_lan"
        if still_demand
        else ("comfy-h3" if motion_demand else None),
    )
    if locked_provider:
        return {
            **common,
            "status": "provider_locked",
            "provider": locked_provider,
            "reason": (
                "the film already locks a motion provider; the armory cannot switch it"
                if motion_demand
                else "the film already locks a still provider; the armory cannot switch it"
            ),
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
    # H3 film-lane is production-selectable when production_promoted; bulk still
    # requires user pilot approval via media-queue / h3 film gates (not silent).
    production_stage = "production" if motion_demand else "production"
    if stage == "pilot_approval":
        production_stage = "pilot"
    allow_experimental = bool(motion_demand)
    try:
        route = select_weapon(
            operation,
            stage=production_stage,
            identity_lock=edit_demand,
            allow_experimental=allow_experimental,
        )
    except ComfyArmoryError as exc:
        if motion_demand:
            return {
                **common,
                "status": "blocked",
                "fail_closed": True,
                "reason": (
                    f"{exc}; free-local default is h3_primary (5090 MiniMax H3); "
                    f"Grok Video 1.5 is technical/explicit 兜底 only (set grok_primary only when no GPU)"
                ),
            }
        return {
            **common,
            "status": "blocked",
            "reason": str(exc),
            "fail_closed": True,
        }
    weapon = route["weapon"]
    pilot_only = (
        bool((weapon.get("capabilities") or {}).get("pilot_only"))
        or str(weapon.get("status") or "") == "experimental"
    )
    promoted = bool((weapon.get("verified") or {}).get("production_promoted"))
    # Motion film-lane: select free, never auto-bulk-execute (queue/h3 run is explicit).
    auto_execute = (not pilot_only) and not motion_demand
    film_cli = str((weapon.get("capabilities") or {}).get("film_workflow_cli") or "").strip()
    if motion_demand and film_cli == "aifilm h3":
        command = "aifilm h3 plan|run --register"
    else:
        command = f"aifilm comfy route --intent {operation}" + (
            " --allow-experimental" if pilot_only else ""
        )
    inventory_tier = "primary" if promoted or not pilot_only else "experimental"
    inventory_line = None
    try:
        from weapon_inventory import inventory_summary_line, primary_for

        inv = primary_for(operation)
        if inv and inv.get("tier"):
            inventory_tier = str(inv["tier"])
        inventory_line = inventory_summary_line()
    except Exception:
        inv = None
    return {
        **common,
        "status": "ready",
        "operation": route.get("operation") or route.get("intent") or operation,
        "quality": route.get("quality") or "max_practical",
        "weapon_id": weapon["id"],
        "provider": str(weapon.get("provider") or "comfy_lan"),
        "source_endpoint": weapon.get("source_endpoint"),
        "command": command,
        "auto_select": True,
        "auto_execute_when_requested": auto_execute,
        "requires_live_probe": True,
        "pilot_only": pilot_only,
        "production_promoted": promoted,
        "pilot_verified": bool((weapon.get("verified") or {}).get("real_pilot")),
        "inventory_tier": inventory_tier,
        "inventory_id": (inv or {}).get("id") if isinstance(inv, dict) else None,
        "inventory_line": inventory_line,
        "reason": (
            "unlocked visual demand maps to MiniMax H3 film-lane (hybrid restricted/meat); "
            "explicit aifilm h3 / media-queue — bulk still needs user pilot approval"
            if motion_demand and promoted
            else (
                "unlocked visual demand maps to the highest-priority local weapon; "
                "experimental motion is pilot-gated and never silent bulk"
                if pilot_only
                else (
                    "unlocked visual demand maps to the highest-priority pilot-verified local weapon; "
                    "the execution command performs current model read-back"
                )
            )
        ),
    }
