from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from comfy_armory import ComfyArmoryError, load_armory, select_weapon  # noqa: E402


def test_armory_contains_no_wan22_i2v_weapon() -> None:
    armory = load_armory()
    assert all(weapon.get("provider") != "comfy-wan22" for weapon in armory["weapons"])
    assert all("wan22" not in str(weapon.get("id") or "") for weapon in armory["weapons"])


def test_armory_promotes_minimax_h3_film_lane() -> None:
    armory = load_armory()
    by_id = {w["id"]: w for w in armory["weapons"]}
    for wid in (
        "minimax-h3-t2v-pilot",
        "minimax-h3-i2v-pilot",
        "minimax-h3-r2v-pilot",
    ):
        weapon = by_id[wid]
        assert weapon["status"] == "verified"
        assert weapon["provider"] == "comfy-h3"
        assert weapon["verified"]["real_pilot"] is True
        assert weapon["verified"]["armory_admitted"] is True
        assert weapon["verified"]["production_promoted"] is True
        assert weapon["capabilities"].get("prefer_native_audio") is True
        assert weapon["capabilities"].get("film_workflow_cli") == "aifilm h3"
        assert weapon["capabilities"].get("pilot_only") is False
        assert weapon["capabilities"].get("bulk_requires_pilot_approval") is True
        receipt = Path(__file__).resolve().parents[1] / weapon["latest_canary_receipt_path"]
        assert receipt.is_file(), f"missing intake evidence for {wid}"
    i2v = by_id["minimax-h3-i2v-pilot"]
    assert i2v["verified"].get("film_workflow_e2e_output_sha256")


def test_armory_registers_minimax_h3_weapons() -> None:
    armory = load_armory()
    ids = {weapon["id"] for weapon in armory["weapons"]}
    assert "minimax-h3-t2v-pilot" in ids
    assert "minimax-h3-i2v-pilot" in ids
    assert "minimax-h3-r2v-pilot" in ids


def test_local_i2v_routes_to_h3_film_lane_production() -> None:
    selected = select_weapon("image-to-video", stage="production")
    assert selected["weapon"]["id"] == "minimax-h3-i2v-pilot"
    assert selected["weapon"]["provider"] == "comfy-h3"
    assert selected["weapon"]["verified"]["production_promoted"] is True


def test_local_t2v_routes_to_h3_film_lane_production() -> None:
    selected = select_weapon("text-to-video", stage="production")
    assert selected["weapon"]["id"] == "minimax-h3-t2v-pilot"


def test_local_i2v_no_longer_requires_experimental_flag() -> None:
    selected = select_weapon("image-to-video", stage="pilot", allow_experimental=False)
    assert selected["weapon"]["id"] == "minimax-h3-i2v-pilot"


def test_adult_meat_production_selects_promoted_h3() -> None:
    selected = select_weapon("adult-meat-motion-i2v", stage="production")
    assert selected["weapon"]["id"] == "minimax-h3-i2v-pilot"
    assert selected["weapon"]["verified"]["production_promoted"] is True


def test_local_identity_edit_remains_available() -> None:
    selected = select_weapon("image-edit", identity_lock=True)
    assert selected["weapon"]["id"] == "qwen-image-edit-2511-local"
