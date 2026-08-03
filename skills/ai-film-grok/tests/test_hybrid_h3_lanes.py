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
