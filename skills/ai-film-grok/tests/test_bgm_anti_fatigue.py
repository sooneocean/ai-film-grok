"""BGM anti-fatigue long-plate checks."""

from __future__ import annotations

import json
from pathlib import Path

from bgm_anti_fatigue import check_bgm_anti_fatigue


def test_short_ok(tmp_path: Path):
    (tmp_path / "film-spec.json").write_text(json.dumps({"title": "t"}), encoding="utf-8")
    rep = check_bgm_anti_fatigue(tmp_path, total_dur_sec=30.0, write=False)
    assert rep["ok"] is True


def test_long_single_loop_risk(tmp_path: Path):
    (tmp_path / "film-spec.json").write_text(json.dumps({"title": "t"}), encoding="utf-8")
    rep = check_bgm_anti_fatigue(
        tmp_path,
        total_dur_sec=200.0,
        bed_source="auto",
        template_mode="auto",
        music_seed=1,
        write=True,
    )
    codes = {i["code"] for i in rep["issues"]}
    assert "BGM_SINGLE_LOOP_RISK" in codes
    assert rep["ok"] is False  # hard at 180+
    assert (tmp_path / "receipts" / "bgm-anti-fatigue.json").is_file()


def test_inject_chapters():
    from bgm_anti_fatigue import inject_anti_fatigue_chapters

    ch = inject_anti_fatigue_chapters([], total_dur_sec=200.0, default_mood="rnb", chapter_sec=45.0)
    assert len(ch) >= 3
    assert ch[0]["motif_id"] != ch[1]["motif_id"] or ch[0]["seed"] != ch[1]["seed"]
    assert ch[-1]["end_sec"] >= 199.0
