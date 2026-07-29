"""Fail-closed provider selection for dialogue performance-state i2i stills."""

from __future__ import annotations

from typing import Any

from frw_canary import frw_i2i_capability

BUSY_CODES = frozenset({"COMFY_QUEUE_BUSY", "VRAM_BELOW_FLOOR", "RAM_BELOW_FLOOR"})
NON_INTERFERENCE = [
    "never_global_interrupt",
    "never_delete_foreign_queue",
    "never_free_memory_while_busy",
]


def _capacity_codes(capacity: dict[str, Any] | None) -> set[str]:
    if not isinstance(capacity, dict):
        return set()
    raw = capacity.get("codes") or capacity.get("blockers") or []
    if isinstance(raw, str):
        raw = [raw]
    return {str(item).strip().upper() for item in raw if str(item).strip()}


def route_dialogue_i2i(
    *,
    frw_receipt: dict[str, Any] | None,
    local_capacity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Choose only a proven route; never take over another 5090 workload.

    ``local_capacity`` is intentionally an explicit input.  State-index is
    read-only planning, so it must not probe, free, interrupt, or submit work.
    """
    common = {
        "schema_version": 1,
        "kind": "dialogue-i2i-route",
        "primary_provider": "frw_i2i",
        "fallback_provider": "comfy_qwen_i2i",
        "non_interference": NON_INTERFERENCE,
    }
    capability = frw_i2i_capability(frw_receipt)
    if capability == "available":
        return {
            **common,
            "status": "ready",
            "selected_provider": "frw_i2i",
            "reason": "FRW upload credential and exact img2image template are proven",
        }

    if local_capacity is None:
        return {
            **common,
            "status": "local_preflight_required",
            "selected_provider": None,
            "frw_i2i_capability": capability,
            "reason": "FRW exact i2i is not proven; run local capacity preflight before fallback",
        }

    codes = _capacity_codes(local_capacity)
    if codes & BUSY_CODES:
        return {
            **common,
            "status": "wait_for_local",
            "selected_provider": None,
            "frw_i2i_capability": capability,
            "blockers": sorted(codes & BUSY_CODES),
            "reason": "local 5090 is occupied; wait rather than interrupt, delete, or evict another job",
        }
    if local_capacity.get("ok") is True:
        return {
            **common,
            "status": "ready",
            "selected_provider": "comfy_qwen_i2i",
            "frw_i2i_capability": capability,
            "reason": "FRW exact i2i is not proven and local capacity preflight passed",
        }
    return {
        **common,
        "status": "blocked",
        "selected_provider": None,
        "frw_i2i_capability": capability,
        "blockers": sorted(codes),
        "reason": "local fallback preflight did not pass; do not silently switch provider",
    }
