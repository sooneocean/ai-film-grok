#!/usr/bin/env python3
"""Cross-modality weapon inventory — single tier table for agents and tests.

Machine truth: registry/weapon-inventory.json
Local Comfy weapons remain in registry/comfy-weapons.json; this module
cross-checks primaries against that armory + known external providers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SKILL_ROOT = Path(__file__).resolve().parents[1]
_INVENTORY = _SKILL_ROOT / "registry" / "weapon-inventory.json"
_COMFY = _SKILL_ROOT / "registry" / "comfy-weapons.json"

_KNOWN_EXTERNAL_IDS = frozenset(
    {
        "motion_prompt_spine",
        "prompt_injector",
        "asset_prompt_hints",
        "grok_chat_agent",
        "grok_cast_image_edit",
        "frw_img2image_still_challenge",
        "qwen-layered-control",
        "minimax-h3-flf",
        "grok_video_1_5",
        "frw_ltx_dialogue",
        "wan22_local_i2v",
        "seedance_primary",
        "edge_tts_zh",
        "mimo_tts",
        "qwen3_tts_audio_node",
        "bgm_recipe_rnb",
        "ace_step15_bgm_library",
        "stable_audio_ambient",
        "mmaudio_sfx",
        "voicebox_tts",
        "elevenlabs_ja_path",
    }
)

_VALID_TIERS = frozenset({"primary", "secondary", "experimental", "retired"})
_REQUIRED_MODALITIES = ("text", "still", "motion", "audio")


class WeaponInventoryError(ValueError):
    """Inventory missing, invalid, or inconsistent with the Comfy armory."""


def inventory_path() -> Path:
    return _INVENTORY


def load_inventory() -> dict[str, Any]:
    try:
        data = json.loads(_INVENTORY.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise WeaponInventoryError(f"cannot read weapon inventory: {exc}") from exc
    if data.get("kind") != "ai-film-weapon-inventory":
        raise WeaponInventoryError("invalid inventory kind")
    modalities = data.get("modalities")
    if not isinstance(modalities, dict):
        raise WeaponInventoryError("inventory.modalities missing")
    for key in _REQUIRED_MODALITIES:
        if key not in modalities:
            raise WeaponInventoryError(f"inventory missing modality: {key}")
        entries = (modalities[key] or {}).get("entries")
        if not isinstance(entries, list) or not entries:
            raise WeaponInventoryError(f"modality {key} has no entries")
    data["ok"] = True
    return data


def _load_comfy_weapon_ids() -> set[str]:
    try:
        armory = json.loads(_COMFY.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    ids: set[str] = set()
    for item in armory.get("weapons") or []:
        if isinstance(item, dict) and item.get("id"):
            ids.add(str(item["id"]))
    return ids


def iter_entries(inventory: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    data = inventory if inventory is not None else load_inventory()
    out: list[dict[str, Any]] = []
    for modality, block in (data.get("modalities") or {}).items():
        if not isinstance(block, dict):
            continue
        for entry in block.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            row = dict(entry)
            row["modality"] = modality
            out.append(row)
    return out


def primaries(inventory: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [e for e in iter_entries(inventory) if str(e.get("tier") or "") == "primary"]


def primary_for(demand_class: str, inventory: dict[str, Any] | None = None) -> dict[str, Any] | None:
    data = inventory if inventory is not None else load_inventory()
    demand = str(demand_class or "").strip().lower()
    if not demand:
        return None
    index = data.get("demand_primary_index") or {}
    primary_id = index.get(demand)
    if primary_id:
        for entry in iter_entries(data):
            if entry.get("id") == primary_id:
                return entry
    for entry in primaries(data):
        classes = [str(c).lower() for c in (entry.get("demand_classes") or [])]
        if demand in classes:
            return entry
    return None


def resolve_registry_weapon_id(entry: dict[str, Any]) -> str | None:
    if entry.get("registry_weapon"):
        return str(entry["registry_weapon"])
    eid = str(entry.get("id") or "")
    if eid == "minimax-h3-flf":
        return "minimax-h3-i2v-pilot"
    if eid in _load_comfy_weapon_ids():
        return eid
    return None


def validate_inventory(*, inventory: dict[str, Any] | None = None) -> dict[str, Any]:
    data = inventory if inventory is not None else load_inventory()
    comfy_ids = _load_comfy_weapon_ids()
    errors: list[str] = []
    warnings: list[str] = []
    primary_rows = primaries(data)

    if not primary_rows:
        errors.append("no primary entries")

    modalities_with_primary: set[str] = set()
    for entry in primary_rows:
        tier = str(entry.get("tier") or "")
        if tier not in _VALID_TIERS:
            errors.append(f"bad tier on {entry.get('id')}: {tier}")
        mid = str(entry.get("modality") or "")
        modalities_with_primary.add(mid)
        eid = str(entry.get("id") or "")
        reg = resolve_registry_weapon_id(entry)
        if reg:
            if reg not in comfy_ids and eid not in _KNOWN_EXTERNAL_IDS:
                errors.append(f"primary {eid} registry_weapon {reg} not in comfy-weapons")
        elif eid not in _KNOWN_EXTERNAL_IDS:
            errors.append(f"primary {eid} is orphan (not comfy weapon and not known external)")

    for m in _REQUIRED_MODALITIES:
        if m not in modalities_with_primary:
            errors.append(f"modality {m} has no primary entry")

    for demand, pid in (data.get("demand_primary_index") or {}).items():
        hit = primary_for(str(demand), data)
        if not hit or hit.get("id") != pid:
            found = next((e for e in iter_entries(data) if e.get("id") == pid), None)
            if not found:
                errors.append(f"demand_primary_index[{demand}] → unknown id {pid}")
            elif str(found.get("tier")) != "primary":
                warnings.append(f"demand_primary_index[{demand}] → {pid} tier={found.get('tier')}")

    try:
        armory = json.loads(_COMFY.read_text(encoding="utf-8"))
        promoted = [
            w
            for w in (armory.get("weapons") or [])
            if isinstance(w, dict)
            and (w.get("verified") or {}).get("production_promoted") is True
        ]
        inv_ids = {e.get("id") for e in iter_entries(data)} | {
            e.get("registry_weapon") for e in iter_entries(data) if e.get("registry_weapon")
        }
        for w in promoted:
            wid = w.get("id")
            if wid and wid not in inv_ids:
                warnings.append(f"comfy production_promoted {wid} missing from inventory")
    except (OSError, ValueError) as exc:
        warnings.append(f"could not cross-check comfy armory: {exc}")

    return {
        "schema_version": 1,
        "kind": "weapon-inventory-validation",
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "primary_count": len(primary_rows),
        "entry_count": len(iter_entries(data)),
        "modalities": list(_REQUIRED_MODALITIES),
    }


def inventory_summary_line(inventory: dict[str, Any] | None = None) -> str:
    data = inventory if inventory is not None else load_inventory()
    parts: list[str] = []
    for modality in _REQUIRED_MODALITIES:
        prims = [
            e["id"]
            for e in (data.get("modalities") or {}).get(modality, {}).get("entries") or []
            if isinstance(e, dict) and e.get("tier") == "primary"
        ]
        if prims:
            parts.append(f"{modality}={'+'.join(prims[:3])}")
    return " · ".join(parts)


def primary_weapon_id_for_router_operation(operation: str) -> str | None:
    entry = primary_for(operation)
    if not entry:
        return None
    return resolve_registry_weapon_id(entry) or (
        str(entry["id"]) if entry.get("id") in _load_comfy_weapon_ids() else None
    )
