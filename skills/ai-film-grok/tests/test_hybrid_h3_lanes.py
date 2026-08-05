from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from film_spec import (  # noqa: E402
    default_i2v_provider,
    resolve_h3_config,
    resolve_i2v_profile,
)
from production_router import build_shot_intent  # noqa: E402


def test_hybrid_h3_profile_keeps_grok_bulk_auto() -> None:
    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "hybrid_h3"}):
        assert resolve_i2v_profile() == "hybrid_h3"
        assert default_i2v_provider() == "grok"
        h3 = resolve_h3_config({})
        assert h3["enabled"] is True
        assert h3["audio_policy"] == "prefer_native"
        assert float(h3["max_duration_sec"]) <= 15


def test_restricted_shot_soft_locks_comfy_h3_when_enabled() -> None:
    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "hybrid_h3"}):
        intent = build_shot_intent(
            {
                "_i2v_profile": "hybrid_h3",
                "h3": {"enabled": True},
                "i2v_provider": "grok",
                "_i2v_provider_explicit": False,
            },
            {
                "id": "s_meat",
                "shot_role": "hero",
                "heat_phase": "act",
                "wardrobe_state": "bare",
            },
        )
    assert intent["content_class"] == "restricted_local"
    assert intent["provider_lock"] == "comfy-h3"
    assert intent["recommended_provider"] == "comfy-h3"
    assert intent["recommended_weapon"] == "minimax-h3-i2v-pilot"
    assert intent["audio_policy"] == "prefer_native"
    assert intent["max_duration_sec"] is not None
    assert float(intent["max_duration_sec"]) <= 15


def test_restricted_without_h3_does_not_force_local_lock() -> None:
    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "grok_primary"}):
        intent = build_shot_intent(
            {
                "_i2v_profile": "grok_primary",
                "h3": {"enabled": False},
                "i2v_provider": "grok",
                "_i2v_provider_explicit": True,
            },
            {
                "id": "s_meat2",
                "shot_role": "hero",
                "heat_phase": "act",
            },
        )
    assert intent["content_class"] == "restricted_local"
    assert intent["recommended_provider"] == "comfy-h3"
    # film-wide grok lock still wins when explicit
    assert intent["provider_lock"] == "grok"


def test_env_shot_recommends_frw_t2v_lane() -> None:
    intent = build_shot_intent(
        {"_i2v_profile": "hybrid_h3", "h3": {"enabled": True}},
        {"id": "s_env", "shot_role": "env"},
    )
    assert intent["operation"] == "text_to_video"
    assert intent["identity_lock"] is False
    assert intent["recommended_provider"] == "frw"


def test_setup_hero_recommends_grok() -> None:
    intent = build_shot_intent(
        {"_i2v_profile": "hybrid_h3", "h3": {"enabled": True}},
        {"id": "s_setup", "shot_role": "hero", "heat_phase": "setup"},
    )
    assert intent["content_class"] == "general"
    assert intent["recommended_provider"] == "grok"
    assert intent["provider_lock"] is None


def test_h3_duration_clamped() -> None:
    cfg = resolve_h3_config({"h3": {"enabled": True, "max_duration_sec": 99}})
    assert float(cfg["max_duration_sec"]) == 15.0
    cfg2 = resolve_h3_config({"h3": {"enabled": True, "max_duration_sec": 1}})
    assert float(cfg2["max_duration_sec"]) == 3.0


def test_adult_genre_auto_enables_h3_under_grok_primary() -> None:
    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "grok_primary"}, clear=False):
        cfg = resolve_h3_config({"genre": "adult", "heat_scale": "max"})
        assert cfg["enabled"] is True
        # Drama without hot heat must not auto dual-lane.
        cfg_drama = resolve_h3_config({"genre": "drama", "heat_scale": ""})
        assert cfg_drama["enabled"] is False
        # Explicit opt-out wins.
        cfg_off = resolve_h3_config(
            {"genre": "adult", "heat_scale": "max", "h3": {"enabled": False}}
        )
        assert cfg_off["enabled"] is False


def test_difficulty_coitus_marks_restricted_without_heat_phase() -> None:
    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "hybrid_h3"}):
        intent = build_shot_intent(
            {"_i2v_profile": "hybrid_h3", "h3": {"enabled": True}},
            {
                "id": "s_hard",
                "shot_role": "hero",
                "coitus_beat": "deep_thrust",
            },
        )
    assert intent["content_class"] == "restricted_local"
    assert intent["provider_lock"] == "comfy-h3"
    assert any("coitus_beat" in f for f in intent.get("difficulty_flags") or [])
    assert intent["recommended_still_provider"] == "comfy_lan"


def test_l4_contact_difficulty() -> None:
    intent = build_shot_intent(
        {"_i2v_profile": "hybrid_h3", "h3": {"enabled": True}},
        {
            "id": "s_l4",
            "shot_role": "hero",
            "shot_size": "l4",
            "contact": True,
            "dsl": {"camera": {"shot_size": "l4"}},
        },
    )
    assert intent["content_class"] == "restricted_local"
    assert "l4_contact:l4" in (intent.get("difficulty_flags") or [])


def test_ltx23_adult_profile_defaults() -> None:
    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "ltx23_adult"}):
        assert resolve_i2v_profile() == "ltx23_adult"
        assert default_i2v_provider() == "frw-ltx23"
        h3 = resolve_h3_config({"genre": "adult", "heat_scale": "max"})
        assert h3["enabled"] is True


def test_ltx23_adult_safe_dialogue_routes_ltx_audio() -> None:
    intent = build_shot_intent(
        {
            "_i2v_profile": "ltx23_adult",
            "h3": {"enabled": True},
            "motion_lanes": {
                "dialogue": "frw_ltx23",
                "dialogue_safe_cloud": "cloud_ltx23_audio",
                "allow_ltx_dialogue": True,
                "restricted_local": "comfy-h3",
            },
        },
        {
            "id": "s_dlg",
            "shot_role": "hero",
            "heat_phase": "setup",
            "screen_mode": "on_camera",
            "spoken_text": "先别急。",
            "speaker": "heroine",
        },
    )
    assert intent["content_class"] == "general"
    assert intent["recommended_lane"] == "cloud_ltx23_audio"
    assert intent["recommended_provider"] == "frw-ltx23"
    assert intent["recommended_weapon"] == "ltx23-img2video-audio"
    assert intent["audio_policy"] == "prefer_native"
    assert intent["provider_lock"] == "frw-ltx23"


def test_ltx23_adult_restricted_meat_never_routes_ltx() -> None:
    intent = build_shot_intent(
        {
            "_i2v_profile": "ltx23_adult",
            "h3": {"enabled": True},
            "motion_lanes": {
                "dialogue": "frw_ltx23",
                "allow_ltx_dialogue": True,
                "restricted_local": "comfy-h3",
            },
        },
        {
            "id": "s_meat_ltx",
            "shot_role": "hero",
            "heat_phase": "act",
            "wardrobe_state": "bare",
            "screen_mode": "on_camera",
            "spoken_text": "再深一点。",
        },
    )
    assert intent["content_class"] == "restricted_local"
    assert intent["recommended_provider"] == "comfy-h3"
    assert intent["provider_lock"] == "comfy-h3"
    assert intent["recommended_weapon"] == "minimax-h3-i2v-pilot"


def test_hybrid_lanes_dialogue_frw_ltx23_safe_audio() -> None:
    intent = build_shot_intent(
        {
            "_i2v_profile": "hybrid_h3",
            "h3": {"enabled": True},
            "motion_lanes": {"dialogue": "frw_ltx23", "allow_ltx_dialogue": True},
        },
        {
            "id": "s_safe_dlg",
            "shot_role": "hero",
            "heat_phase": "setup",
            "screen_mode": "on_camera",
            "spoken_text": "今晚有空吗？",
        },
    )
    assert intent["recommended_provider"] == "frw-ltx23"
    assert intent["recommended_lane"] == "cloud_ltx23_audio"
    # hybrid does not hard-lock provider unless profile is ltx23_*
    assert intent["provider_lock"] is None


def test_next_actions_ltx23_adult_surfaces_audio_and_still_repair(tmp_path: Path) -> None:
    from next_actions import build_next_actions

    (tmp_path / "receipts").mkdir(parents=True)
    (tmp_path / "film-spec.json").write_text(
        __import__("json").dumps(
            {
                "title": "ltx fixture",
                "_i2v_profile": "ltx23_adult",
                "h3": {"enabled": True},
                "motion_lanes": {
                    "dialogue": "frw_ltx23",
                    "allow_ltx_dialogue": True,
                    "restricted_local": "comfy-h3",
                },
                "scenes": [{"id": "s1", "shots": [{"id": "shot01", "shot_role": "hero"}]}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "receipts" / "pilot-approval.json").write_text(
        __import__("json").dumps(
            {
                "approved": True,
                "approved_by": "user",
                "user_phrase": "pilot 过",
                "shots": ["shot01", "shot02", "shot03"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "receipts" / "bulk-preflight.json").write_text(
        __import__("json").dumps({"ok": True}),
        encoding="utf-8",
    )
    actions = build_next_actions(
        tmp_path,
        gates={
            "brief": True,
            "style_locked": True,
            "spec": True,
            "clips_complete": False,
            "final_complete": False,
        },
    )
    ids = [a["id"] for a in actions]
    assert "frw-ltx23-canary" in ids
    assert "frw-ltx23-audio-unit" in ids
    assert "still-challenge-repair" in ids
    assert "h3-lane-meat" in ids
