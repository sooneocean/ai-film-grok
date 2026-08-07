"""Film Production OS W3–W4: coverage, storyboard, scene drama, continuity audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from continuity_audit import audit_continuity_chain, continuity_audit_at_root  # noqa: E402
from coverage_check import (  # noqa: E402
    CODE_COVERAGE_INCOMPLETE,
    CODE_UNEDITABLE_PREDICTED,
    check_scene_coverage,
    check_spec_coverage,
    coverage_check_at_root,
    infer_coverage_role,
)
from scene_drama import lint_scene_drama, scene_drama_at_root  # noqa: E402
from storyboard_status import (  # noqa: E402
    check_storyboard_gate,
    set_storyboard_status,
)


def test_infer_coverage_role_from_purpose():
    assert infer_coverage_role({"shot_purpose": "establish_location"}) == "establish"
    assert infer_coverage_role({"shot_purpose": "show_reaction"}) == "reaction"
    assert infer_coverage_role({"shot_purpose": "emotional_closeup"}) == "close_up"
    assert infer_coverage_role({"dsl": {"shot_size": "cu"}}) == "close_up"


def test_scene_coverage_weak_flags_soft():
    scene = {
        "id": "sc01",
        "shots": [
            {"id": "s1", "shot_purpose": "action_coverage"},
            {"id": "s2", "shot_purpose": "action_coverage"},
            {"id": "s3", "shot_purpose": "action_coverage"},
        ],
    }
    soft = check_scene_coverage(scene, strict=False)
    assert CODE_UNEDITABLE_PREDICTED in soft["codes"]
    assert soft["ok"] is True  # warning only when not strict
    hard = check_scene_coverage(scene, strict=True)
    assert hard["ok"] is False
    assert hard["production_allowed"] is False


def test_scene_coverage_variety_ok():
    scene = {
        "id": "sc01",
        "shots": [
            {"id": "s1", "shot_purpose": "establish_location"},
            {"id": "s2", "shot_purpose": "emotional_closeup"},
            {"id": "s3", "shot_purpose": "show_reaction"},
            {"id": "s4", "shot_purpose": "action_coverage"},
        ],
    }
    rep = check_scene_coverage(scene, strict=True)
    assert rep["ok"] is True
    assert "establish" in rep["roles_present"]
    assert "reaction" in rep["roles_present"]


def test_coverage_check_at_root(tmp_path: Path):
    spec = {
        "title": "cov",
        "production_mode": "shortform",
        "scenes": [
            {
                "id": "sc01",
                "shots": [
                    {"id": "a", "shot_purpose": "establish_location"},
                    {"id": "b", "shot_purpose": "show_reaction"},
                ],
            }
        ],
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (tmp_path / "receipts").mkdir()
    rep = coverage_check_at_root(tmp_path, strict=False, write_receipt=True)
    assert rep["ok"] is True
    assert (tmp_path / "receipts" / "coverage-check.json").is_file()


def test_storyboard_approve_gate(tmp_path: Path):
    (tmp_path / "film-spec.json").write_text(json.dumps({"title": "sb"}), encoding="utf-8")
    (tmp_path / "receipts").mkdir()
    missing = check_storyboard_gate(tmp_path, strict=True)
    assert missing["ok"] is False
    assert missing["keyframe_bulk_allowed"] is False
    set_storyboard_status(tmp_path, status="review")
    mid = check_storyboard_gate(tmp_path, strict=True)
    assert mid["ok"] is False
    bad = set_storyboard_status(tmp_path, status="approved")
    assert bad.get("ok") is False  # needs user phrase
    ok = set_storyboard_status(
        tmp_path, status="approved", user_phrase="分镜已批，可进 keyframe"
    )
    assert ok["ok"] is True
    gate = check_storyboard_gate(tmp_path, strict=True)
    assert gate["ok"] is True
    assert gate["keyframe_bulk_allowed"] is True


def test_scene_drama_strict_fields():
    weak = lint_scene_drama({"id": "sc1"}, strict=True)
    assert weak["ok"] is False
    assert "SCENE_DRAMA_FIELD_MISSING" in weak["codes"]
    strong = lint_scene_drama(
        {
            "id": "sc1",
            "dramatic_goal": "赢得信任",
            "conflict": "她隐瞒身份",
            "scene_turn": "钥匙落地",
            "emotional_arc": {"start": "戒备", "mid": "动摇", "end": "依赖"},
            "continuity_in": {"wardrobe": "coat"},
            "continuity_out": {"wardrobe": "bare"},
        },
        strict=True,
    )
    assert strong["ok"] is True


def test_continuity_chain_break():
    spec = {
        "scenes": [
            {
                "id": "sc01",
                "shots": [
                    {
                        "id": "s1",
                        "continuity_in": {"wardrobe": "coat"},
                        "continuity_out": {"wardrobe": "bare"},
                    },
                    {
                        "id": "s2",
                        "continuity_in": {"wardrobe": "coat"},  # rewind
                        "continuity_out": {"wardrobe": "coat"},
                    },
                ],
            }
        ]
    }
    soft = audit_continuity_chain(spec, strict=False)
    assert soft["ok"] is True
    assert "CONTINUITY_WARDROBE_REWIND" in soft["codes"] or "CONTINUITY_BREAK" in soft["codes"]
    hard = audit_continuity_chain(spec, strict=True)
    assert hard["ok"] is False
    assert hard["picture_lock_allowed"] is False


def test_continuity_and_scene_drama_root(tmp_path: Path):
    spec = {
        "title": "w4",
        "scene_strict": True,
        "scenes": [
            {
                "id": "sc01",
                "dramatic_goal": "靠近",
                "conflict": "距离",
                "scene_turn": "触碰",
                "emotional_arc": {"start": "冷", "mid": "温", "end": "热"},
                "continuity_in": {"prop": "key"},
                "continuity_out": {"prop": "key"},
                "shots": [
                    {
                        "id": "s1",
                        "continuity_in": {"prop": "key"},
                        "continuity_out": {"prop": "key"},
                    }
                ],
            }
        ],
    }
    (tmp_path / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    (tmp_path / "receipts").mkdir()
    d = scene_drama_at_root(tmp_path, write_receipt=True)
    assert d["ok"] is True
    c = continuity_audit_at_root(tmp_path, write_receipt=True)
    assert c["ok"] is True
    assert (tmp_path / "receipts" / "scene-drama.json").is_file()
    assert (tmp_path / "receipts" / "continuity-audit.json").is_file()


def test_spec_coverage_aggregate():
    rep = check_spec_coverage(
        {
            "production_mode": "shortform",
            "scenes": [
                {
                    "id": "sc01",
                    "shots": [
                        {"id": "a", "shot_purpose": "establish_location"},
                        {"id": "b", "shot_purpose": "show_reaction"},
                    ],
                }
            ],
        },
        strict=True,
    )
    assert rep["ok"] is True
    assert rep["scene_count"] == 1
