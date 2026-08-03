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


@pytest.mark.parametrize("operation", ["image-to-video", "i2v", "adult-meat-motion-i2v"])
def test_local_i2v_is_retired(operation: str) -> None:
    with pytest.raises(ComfyArmoryError, match="WAN22_I2V_RETIRED"):
        select_weapon(operation, stage="pilot", allow_experimental=True)


def test_local_identity_edit_remains_available() -> None:
    selected = select_weapon("image-edit", identity_lock=True)
    assert selected["weapon"]["id"] == "qwen-image-edit-2511-local"
