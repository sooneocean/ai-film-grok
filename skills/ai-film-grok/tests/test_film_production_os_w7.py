"""Film Production OS W7: performance direction, sound cues, cine rules, asset versions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from asset_version import register_asset_version, resolve_approved_version  # noqa: E402
from cine_rules import lookup_cine_rule  # noqa: E402
from cinematography_rules import map_intent_to_camera, resolve_shot_cinematography  # noqa: E402
from performance_cue import normalize_performance_cue  # noqa: E402
from performance_direction import (  # noqa: E402
    CODE_PERF_EMOTION_ONLY,
    lint_performance_direction,
    normalize_performance_direction,
)
from sound_cue_model import collect_sound_cues_from_spec, normalize_sound_cue  # noqa: E402


def test_performance_direction_rejects_emotion_only_strict():
    rep = lint_performance_direction(
        {"id": "s1", "performance": {"emotion": "angry"}},
        strict=True,
    )
    assert rep["ok"] is False
    assert CODE_PERF_EMOTION_ONLY in rep["codes"]
    rich = lint_performance_direction(
        {
            "id": "s1",
            "performance_direction": {
                "emotion": "angry",
                "objective": "逼对方开口",
                "subtext": "其实心虚",
                "eye_behavior": "stare then break",
            },
        },
        strict=True,
    )
    assert rich["ok"] is True
    assert rich["normalized"]["objective"]


def test_performance_cue_acting_layer():
    cue = normalize_performance_cue(
        {
            "emotion": "tender",
            "objective": "靠近",
            "subtext": "怕被拒绝",
            "eye": "soft",
            "breath": "held",
            "tempo": "slow",
        }
    )
    assert cue["objective"] == "靠近"
    assert cue["tempo"] == "slow"


def test_sound_cue_and_collect():
    c = normalize_sound_cue(
        {"type": "ambience", "source": "rain_loop", "continues_into_next_shot": True}
    )
    assert c["type"] == "ambience"
    assert c["continuity"]["continues_into_next_shot"] is True
    cues = collect_sound_cues_from_spec(
        {
            "scenes": [
                {
                    "id": "sc01",
                    "shots": [
                        {
                            "id": "s1",
                            "spoken_text": "你好",
                            "sound_cues": [{"type": "sfx", "source": "door_click"}],
                        }
                    ],
                }
            ]
        }
    )
    types = {x["type"] for x in cues}
    assert "dialogue" in types
    assert "sfx" in types


def test_cine_rules_dual_tables():
    look = lookup_cine_rule(purpose="create_tension")
    assert look["matched"] is True
    mapped = map_intent_to_camera("isolation")
    assert mapped is not None
    assert mapped["intent"] == "emotional_isolation"
    resolved = resolve_shot_cinematography(
        {"id": "s1", "shot_purpose": "emotional_closeup"}
    )
    assert resolved["instruction"]


def test_asset_version_chain(tmp_path: Path):
    (tmp_path / "receipts").mkdir()
    r1 = register_asset_version(
        tmp_path, asset_id="CHAR_hero", version="v01", status="draft"
    )
    assert r1["ok"] is True
    r2 = register_asset_version(
        tmp_path,
        asset_id="CHAR_hero",
        version="v02",
        parent_version="v01",
        status="approved",
        path="cast/hero_v02.png",
    )
    assert r2["ok"] is True
    res = resolve_approved_version(tmp_path, "CHAR_hero")
    assert res["ok"] is True
    assert res["approved"]["version"] == "v02"
