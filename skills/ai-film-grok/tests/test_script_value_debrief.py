"""Tests for script-value-debrief (presentation value L0–L4)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
sys.path.insert(0, str(SCRIPTS))

from script_value_debrief import (  # noqa: E402
    check_root,
    confirm_debrief,
    map_beats_to_shot_ids,
    merge_pilot_shot_preference,
    pilot_shortlist_from_debrief,
    score_debrief,
    seed_from_reception,
    user_facing_summary,
    validate_debrief,
    write_debrief,
)
from story_quality import check_story_quality, score_story  # noqa: E402


def _good_debrief() -> dict:
    path = TEMPLATES / "script-value-debrief.example.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _bad_debrief() -> dict:
    return {
        "kind": "script-value-debrief",
        "viewer_promise": "",
        "must_keep_beat_ids": ["only_one"],
        "beat_cards": [
            {"beat_id": "b1", "visual_event": "", "value_rank": 3},
        ],
        "confirmed_by_user": False,
    }


class TestValidateDebrief:
    def test_missing_soft(self):
        rep = validate_debrief(None, strict=False)
        assert rep["ok"] is True
        assert rep["present"] is False
        assert any(w["code"] == "DEBRIEF_MISSING" for w in rep["warnings"])

    def test_missing_strict(self):
        rep = validate_debrief(None, strict=True)
        assert rep["ok"] is False
        assert any(e["code"] == "DEBRIEF_MISSING" for e in rep["errors"])

    def test_good_template(self):
        deb = _good_debrief()
        rep = validate_debrief(deb, strict=False)
        assert rep["ok"] is True
        assert rep["present"] is True
        assert len(rep["pilot_shortlist_beat_ids"]) >= 1
        scores = score_debrief(deb)
        assert scores["overall"] >= 0.5
        assert scores["beat_value_coverage"] > 0.8

    def test_bad_structure(self):
        rep = validate_debrief(_bad_debrief(), strict=True)
        assert rep["ok"] is False
        codes = {e["code"] for e in rep["errors"]}
        assert "DEBRIEF_PROMISE_MISSING" in codes
        assert "DEBRIEF_MUST_KEEP_FEW" in codes
        assert "DEBRIEF_VISUAL_EVENT_MISSING" in codes

    def test_strict_requires_confirm(self):
        deb = _good_debrief()
        deb["confirmed_by_user"] = False
        rep = validate_debrief(deb, strict=True)
        assert any(e["code"] == "DEBRIEF_NOT_CONFIRMED" for e in rep["errors"])


class TestPilotMap:
    def test_shortlist_explicit(self):
        deb = _good_debrief()
        ids = pilot_shortlist_from_debrief(deb)
        assert "beat_hook_latch" in ids

    def test_map_and_merge(self):
        deb = {
            "pilot_shortlist_beat_ids": ["beat_climax"],
            "beat_cards": [
                {
                    "beat_id": "beat_climax",
                    "dramatic_function": "climax",
                    "value_rank": 5,
                    "visual_event": "open door",
                }
            ],
        }
        spec = {
            "scenes": [
                {
                    "shots": [
                        {"id": "shot01", "dramatic_function": "hook"},
                        {"id": "shot02", "dramatic_function": "climax"},
                        {"id": "shot03", "dramatic_function": "bridge"},
                    ]
                }
            ]
        }
        mapped = map_beats_to_shot_ids(deb, spec)
        assert mapped == ["shot02"]
        merged = merge_pilot_shot_preference(["shot01", "shot03"], mapped, n=3)
        assert merged[0] == "shot02"
        assert "shot01" in merged


class TestRootAndQuality:
    def test_write_and_check_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            deb = _good_debrief()
            deb["confirmed_by_user"] = True
            write_debrief(root, deb)
            rep = check_root(root, strict=True)
            assert rep["ok"] is True
            assert rep["present"] is True

    def test_story_quality_with_debrief(self):
        graph = {
            "story": {
                "logline": "面对冲突与危险，付出代价决出胜负",
                "opposition": "极大的阻力",
                "stakes": "生命危险",
                "emotional_arc": ["setup", "confrontation", "resolution"],
                "climax_choice": "勇敢面对",
                "ending_hook": "留下一束光",
                "act_structure": {
                    "setup_ratio": 0.20,
                    "confrontation_ratio": 0.50,
                    "resolution_ratio": 0.30,
                },
            }
        }
        scores_plain = score_story(graph)
        assert scores_plain["debrief_present"] == 0.0
        # Neutral value dims must not tank overall
        assert scores_plain["overall"] > 0.6

        deb = _good_debrief()
        scores = score_story(graph, debrief=deb)
        assert scores["debrief_present"] == 1.0
        assert scores["promise_clarity"] > 0.5
        res = check_story_quality(graph, debrief=deb)
        assert res["ok"] is True

    def test_require_debrief_fails(self):
        graph = {"story": {"logline": "x", "opposition": "a", "stakes": "b"}}
        res = check_story_quality(graph, require_debrief=True)
        assert res["ok"] is False
        assert "debrief_missing" in res["issues"]

    def test_plan_validate_attaches(self):
        from script_value_debrief import attach_to_plan_validate

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = {"ok": True, "issues": []}
            out = attach_to_plan_validate(report, root, strict=False)
            assert "script_value_debrief" in out
            assert out["ok"] is True  # soft missing

            out2 = attach_to_plan_validate({"ok": True}, root, strict=True)
            assert out2["ok"] is False

    def test_adult_template_valid(self):
        path = TEMPLATES / "script-value-debrief.adult-max.example.json"
        deb = json.loads(path.read_text(encoding="utf-8"))
        rep = validate_debrief(deb, strict=False)
        assert rep["ok"] is True
        assert any(
            r >= 4
            for r in [
                int(c.get("value_rank") or 0)
                for c in deb.get("beat_cards") or []
                if isinstance(c, dict)
            ]
        )


class TestSeedConfirmSummary:
    def test_seed_and_confirm(self):
        reception = {
            "schema_version": 1,
            "kind": "story-reception",
            "source": {
                "raw_text": "雨夜她打开门闩。",
                "sha256": __import__("hashlib").sha256("雨夜她打开门闩。".encode()).hexdigest(),
                "language": "zh",
                "source_ref": "test",
            },
            "fidelity": {
                "immutable_facts": ["雨夜"],
                "protected_dialogue": [],
                "explicit_constraints": ["零旁白"],
                "unknowns": [],
            },
            "treatment": {
                "title": "门廊",
                "logline": "暴雨夜她要不要开门",
                "protagonist_goal": "确认门外的人",
                "opposition": "信任裂痕",
                "stakes": "关系",
                "climax_choice": "拉开闩",
                "ending_hook": "空廊脚印",
                "planning_text": "完整可拍规划文本足够长用于测试。",
                "provenance": {
                    "title": "source_supported",
                    "logline": "creative_suggestion",
                    "planning_text": "creative_suggestion",
                    "protagonist_goal": "source_supported",
                    "opposition": "source_supported",
                    "stakes": "source_supported",
                    "climax_choice": "source_supported",
                    "ending_hook": "source_supported",
                },
            },
        }
        draft = seed_from_reception(reception)
        assert draft["kind"] == "script-value-debrief"
        assert draft["confirmed_by_user"] is False
        assert "零旁白" in draft["user_brief"]["must_not"]
        # complete minimal fields for confirm
        draft["viewer_promise"] = "暴雨夜她必须决定是否开门"
        draft["must_keep_beat_ids"] = ["beat_a", "beat_b"]
        draft["beat_cards"] = [
            {
                "beat_id": "beat_a",
                "visual_event": "闪电照门闩",
                "value_rank": 5,
                "state_in": "关",
                "state_out": "惊",
            },
            {
                "beat_id": "beat_b",
                "visual_event": "拉开门闩",
                "value_rank": 5,
                "state_in": "惊",
                "state_out": "开",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            write_debrief(root, draft)
            summary = user_facing_summary(draft)
            assert summary["viewer_promise"]
            assert len(summary["must_keep"]) == 2
            out = confirm_debrief(root, user_phrase="确认 promise 与不可砍")
            assert out["ok"] is True
            assert out["confirmed_by_user"] is True

    def test_confirm_rejects_empty_phrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            deb = _good_debrief()
            write_debrief(root, deb)
            with pytest.raises(ValueError, match="user-phrase"):
                confirm_debrief(root, user_phrase="  ")


class TestSeedConfirmCli:
    def test_seed_and_confirm(self):
        import hashlib

        raw = "成年男女雨夜重逢。"
        reception = {
            "treatment": {
                "title": "雨",
                "logline": "雨夜决定是否开门",
                "protagonist_goal": "确认信任",
                "opposition": "旧伤",
                "stakes": "错过",
                "climax_choice": "开门",
                "ending_hook": "脚印",
                "scene_beats": ["落锁", "对视", "开门"],
            },
            "source": {"sha256": hashlib.sha256(raw.encode()).hexdigest(), "raw_text": raw},
            "fidelity": {"explicit_constraints": ["自愿"], "unknowns": []},
        }
        draft = seed_from_reception(reception)
        assert draft["viewer_promise"]
        assert len(draft["beat_cards"]) == 3
        assert len(draft["must_keep_beat_ids"]) >= 2
        summary = user_facing_summary(draft)
        assert "prompt_user" in summary

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            # fill ranks high + user brief for structure
            draft["user_brief"]["must_have"] = ["开门选择可见"]
            draft["confirmed_by_user"] = False
            for c in draft["beat_cards"]:
                c["value_rank"] = 4
                c["state_in"] = "a"
                c["state_out"] = "b"
            write_debrief(root, draft)
            out = confirm_debrief(root, user_phrase="确认 promise 与不可砍 beat")
            assert out["confirmed_by_user"] is True
            assert load_debrief_ok(root)

    def test_plan_debrief_status(self):
        from argparse import Namespace

        from cli_plan import run_debrief

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            report, code = run_debrief(
                Namespace(
                    action="status",
                    strict=False,
                    file=None,
                    user_phrase=None,
                    force=False,
                    receipt=None,
                ),
                root,
            )
            assert code == 0
            assert report.get("present") is False


def load_debrief_ok(root: Path) -> bool:
    from script_value_debrief import load_debrief

    d = load_debrief(root)
    return bool(d and d.get("confirmed_by_user") is True)


class TestPilotPackPreference:
    def test_pilot_pack_includes_value_pref(self):
        from pilot_pack import pilot_pack
        from util import write_json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            write_json(
                root / "film-spec.json",
                {
                    "title": "t",
                    "heat_scale": "warm",
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "shot01",
                                    "dramatic_function": "hook",
                                    "duration_sec": 6,
                                    "dsl": {"motion": "push"},
                                },
                                {
                                    "id": "shot02",
                                    "dramatic_function": "climax",
                                    "duration_sec": 6,
                                    "dsl": {"motion": "action"},
                                },
                            ]
                        }
                    ],
                },
            )
            write_json(root / "manifest.json", {"stills": {}, "clips": {}})
            deb = _good_debrief()
            # Map climax card to function climax
            deb["pilot_shortlist_beat_ids"] = ["beat_climax_unlatch"]
            deb["beat_cards"] = [
                {
                    "beat_id": "beat_climax_unlatch",
                    "dramatic_function": "climax",
                    "value_rank": 5,
                    "visual_event": "unlatch",
                    "state_in": "a",
                    "state_out": "b",
                },
                {
                    "beat_id": "beat_hook_latch",
                    "dramatic_function": "hook",
                    "value_rank": 5,
                    "visual_event": "latch",
                    "state_in": "a",
                    "state_out": "b",
                },
            ]
            deb["must_keep_beat_ids"] = ["beat_climax_unlatch", "beat_hook_latch"]
            deb["viewer_promise"] = "test promise long enough"
            deb["user_brief"] = {
                "must_have": ["x"],
                "must_not": ["y"],
                "audience_profile": "general",
            }
            write_debrief(root, deb)
            payload = pilot_pack(root)
            pref = payload.get("script_value_preference") or {}
            assert pref.get("applied") is True
            assert "shot02" in (pref.get("mapped_shot_ids") or [])
