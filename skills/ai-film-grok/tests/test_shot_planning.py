"""Unit tests for shot_planning module (extracted from story_plan.py)."""

from __future__ import annotations

from shot_planning import (
    DRAMATIC_FUNCS,
    _camera_axis,
    _motion_text,
    _production_mode,
    _vertical_composition,
)


class TestDramaticFuncs:
    def test_is_tuple(self):
        assert isinstance(DRAMATIC_FUNCS, tuple)

    def test_seven_values(self):
        assert len(DRAMATIC_FUNCS) == 7
        expected = {"hook", "approach", "sensory", "reaction", "action", "afterglow", "bridge"}
        assert set(DRAMATIC_FUNCS) == expected


class TestVerticalComposition:
    def test_hook_action_is_center(self):
        assert _vertical_composition(0, "hook") == "center-subject"
        assert _vertical_composition(0, "action") == "center-subject"

    def test_sensory_even_order(self):
        assert _vertical_composition(2, "sensory") == "three-layer-depth"

    def test_sensory_odd_order(self):
        assert _vertical_composition(1, "sensory") == "foreground-background"

    def test_approach_even_order(self):
        assert _vertical_composition(2, "approach") == "two-character-stack"

    def test_approach_odd_order(self):
        assert _vertical_composition(1, "approach") == "center-subject"

    def test_default_is_center(self):
        assert _vertical_composition(99, "reaction") == "center-subject"
        assert _vertical_composition(99, "bridge") == "center-subject"


class TestCameraAxis:
    def test_base_axes(self):
        assert _camera_axis("approach", 1) == "pan_with"
        assert _camera_axis("sensory", 1) == "low_lean"
        assert _camera_axis("reaction", 1) == "ecu_hold"
        assert _camera_axis("afterglow", 1) == "pull_back"
        assert _camera_axis("bridge", 1) == "locked"

    def test_dolly_in_becomes_ecu_at_multiple_of_three_plus_one(self):
        # idx % 3 == 1 → ecu_hold only for dolly_in base beats
        assert _camera_axis("hook", 1) == "ecu_hold"
        assert _camera_axis("hook", 4) == "ecu_hold"
        assert _camera_axis("hook", 2) == "dolly_in"
        assert _camera_axis("hook", 3) == "dolly_in"
        assert _camera_axis("action", 1) == "ecu_hold"
        assert _camera_axis("action", 4) == "ecu_hold"

    def test_non_dolly_base_unchanged(self):
        assert _camera_axis("approach", 1) == "pan_with"
        assert _camera_axis("sensory", 4) == "low_lean"
        assert _camera_axis("reaction", 7) == "ecu_hold"

    def test_unknown_df_defaults_to_dolly(self):
        assert _camera_axis("unknown", 1) == "ecu_hold"
        assert _camera_axis("unknown", 2) == "dolly_in"


class TestMotionText:
    def test_all_axes_have_text(self):
        for axis in ("dolly_in", "pan_with", "low_lean", "ecu_hold", "pull_back", "locked"):
            text = _motion_text(axis)
            assert isinstance(text, str) and len(text) > 10

    def test_unknown_axis_fallback(self):
        text = _motion_text("nonexistent")
        assert isinstance(text, str) and "restrained" in text


class TestProductionMode:
    def test_env_role_is_t2v(self):
        assert _production_mode("hook", "env") == "text-to-video"
        assert _production_mode("action", "env") == "text-to-video"

    def test_bridge_and_afterglow_panel_animation(self):
        assert _production_mode("bridge", "hero") == "panel-animation"
        assert _production_mode("afterglow", "hero") == "panel-animation"

    def test_action_sensory_hook_i2v(self):
        assert _production_mode("action", "hero") == "single-keyframe-i2v"
        assert _production_mode("sensory", "hero") == "single-keyframe-i2v"
        assert _production_mode("hook", "hero") == "single-keyframe-i2v"

    def test_default_i2v(self):
        assert _production_mode("reaction", "hero") == "single-keyframe-i2v"
        assert _production_mode("approach", "hero") == "single-keyframe-i2v"
