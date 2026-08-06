"""Dialogue performance-state i2i routing must stay capability- and queue-safe."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from dialogue_i2i_route import route_dialogue_i2i  # noqa: E402
from frw_canary import _classify, frw_i2i_capability  # noqa: E402


def test_frw_i2i_requires_exact_still_probe_and_upload_credential() -> None:
    old_video_only = {
        "upload_token": "ok",
        "seedance_i2v": "201_submitted:video-task",
        "ltx_t2v": "201_submitted:t2v-task",
    }
    assert frw_i2i_capability(old_video_only) == "untested"

    blocked = _classify({"upload_token": "ok", "classic_img2image": "403:forbidden"})
    assert blocked["i2i_capability"] == "blocked"

    proven = _classify({"upload_token": "ok", "classic_img2image": "201_submitted:i2i-task"})
    assert proven["i2i_capability"] == "available"


def test_route_prefers_qwen_even_when_frw_i2i_is_proven() -> None:
    route = route_dialogue_i2i(
        frw_receipt={"i2i_capability": "available"},
        local_capacity={"ok": True},
    )
    assert route["status"] == "ready"
    assert route["selected_provider"] == "comfy_qwen_i2i"


def test_frw_requires_explicit_fallback_authorization() -> None:
    route = route_dialogue_i2i(
        frw_receipt={"i2i_capability": "available"},
        local_capacity={"ok": False, "codes": ["QWEN_UNAVAILABLE"]},
        allow_frw_fallback=True,
    )
    assert route["selected_provider"] == "frw_i2i"
    assert "explicit FRW fallback" in route["reason"]


def test_frw_fallback_rejects_unknown_or_incomplete_qwen_capacity() -> None:
    for local_capacity in ({}, {"ok": False}, {"ok": False, "codes": ["UNKNOWN"]}):
        route = route_dialogue_i2i(
            frw_receipt={"i2i_capability": "available"},
            local_capacity=local_capacity,
            allow_frw_fallback=True,
        )
        assert route["status"] == "blocked"
        assert route["selected_provider"] is None


def test_route_waits_for_busy_local_without_interference() -> None:
    route = route_dialogue_i2i(
        frw_receipt={"i2i_capability": "blocked"},
        local_capacity={"ok": False, "codes": ["COMFY_QUEUE_BUSY", "VRAM_BELOW_FLOOR"]},
    )
    assert route["status"] == "wait_for_local"
    assert route["selected_provider"] is None
    assert route["blockers"] == ["COMFY_QUEUE_BUSY", "VRAM_BELOW_FLOOR"]
    assert "never_global_interrupt" in route["non_interference"]


def test_route_requires_local_preflight_when_frw_is_not_proven() -> None:
    route = route_dialogue_i2i(frw_receipt={"i2i_capability": "untested"})
    assert route["status"] == "local_preflight_required"
    assert route["selected_provider"] is None
