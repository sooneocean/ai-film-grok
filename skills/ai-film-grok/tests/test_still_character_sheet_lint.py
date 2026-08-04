"""huangdao 2026-08-03: character sheet path hard-fail; story still passes."""

from __future__ import annotations

from pathlib import Path

from media_qa import lint_still_not_character_sheet


def test_sheet_token_hard_fails(tmp_path: Path) -> None:
    # minimal valid RGB png
    from PIL import Image

    p = tmp_path / "hero_character-sheet.png"
    Image.new("RGB", (704, 1280), (240, 240, 240)).save(p)
    r = lint_still_not_character_sheet(p)
    assert r["ok"] is False
    assert "STILL_LOOKS_LIKE_CHARACTER_SHEET" in r["codes"]


def test_normal_name_ok(tmp_path: Path) -> None:
    from PIL import Image

    p = tmp_path / "ep01_sc01_bt01_sh01.png"
    Image.new("RGB", (704, 1280), (30, 80, 120)).save(p)
    r = lint_still_not_character_sheet(p)
    assert r["ok"] is True
    assert "STILL_LOOKS_LIKE_CHARACTER_SHEET" not in r.get("codes", [])
