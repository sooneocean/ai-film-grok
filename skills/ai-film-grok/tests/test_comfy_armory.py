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


def test_armory_registers_minimax_h3_weapons() -> None:
    armory = load_armory()
    ids = {weapon["id"] for weapon in armory["weapons"]}
    assert "minimax-h3-t2v-pilot" in ids
    assert "minimax-h3-i2v-pilot" in ids
    assert "minimax-h3-r2v-pilot" in ids


def test_local_i2v_routes_to_h3_experimental_pilot() -> None:
    selected = select_weapon(
        "image-to-video",
        stage="pilot",
        allow_experimental=True,
    )
    assert selected["weapon"]["id"] == "minimax-h3-i2v-pilot"
    assert selected["weapon"]["provider"] == "comfy-h3"


def test_local_t2v_routes_to_h3_experimental_pilot() -> None:
    selected = select_weapon(
        "text-to-video",
        stage="pilot",
        allow_experimental=True,
    )
    assert selected["weapon"]["id"] == "minimax-h3-t2v-pilot"


def test_local_i2v_pilot_requires_experimental_flag() -> None:
    with pytest.raises(ComfyArmoryError, match="experimental authorization"):
        select_weapon("image-to-video", stage="pilot", allow_experimental=False)


def test_local_i2v_production_fail_closed_until_promoted() -> None:
    with pytest.raises(ComfyArmoryError, match="no verified weapon"):
        select_weapon("image-to-video", stage="production")


def test_adult_meat_production_still_fail_closed() -> None:
    with pytest.raises(ComfyArmoryError, match="adult meat-motion production gate"):
        select_weapon("adult-meat-motion-i2v", stage="production", allow_experimental=True)


def test_local_identity_edit_remains_available() -> None:
    selected = select_weapon("image-edit", identity_lock=True)
    assert selected["weapon"]["id"] == "qwen-image-edit-2511-local"
