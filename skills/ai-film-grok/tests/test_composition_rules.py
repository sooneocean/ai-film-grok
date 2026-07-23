"""Tests for P1-7: storyboard + composition rules lint.

Verifies:
- Panel schema has new storyboard fields (shot_number, composition_rule, camera_height, etc.)
- lint_composition_rules detects 180° axis breaks
- lint_composition_rules detects 30-degree rule violations
- lint_composition_rules detects eyeline mismatches
- lint_composition_rules detects size progression flatness
- No issues when shots are clean
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from framing_lint import (
    CODE_AXIS_BREAK,
    CODE_EYELINE_MISMATCH,
    CODE_SIZE_PROGRESSION_FLAT,
    CODE_THIRTY_DEGREE_VIOLATION,
    lint_composition_rules,
)


class TestPanelSchemaFields:
    """Panel schema has new storyboard fields."""

    def test_panel_has_storyboard_fields(self):
        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "drama-graph.schema.json"
        schema = json.loads(schema_path.read_text())
        panel = schema.get("$defs", {}).get("Panel", {})
        props = panel.get("properties", {})
        assert "shot_number" in props
        assert "composition_rule" in props
        assert "camera_height" in props
        assert "lens_mm" in props
        assert "eyeline_target" in props
        assert "axis_side" in props
        assert "transition_to_next" in props
        assert "shot_size_progression" in props

    def test_composition_rule_enum(self):
        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "drama-graph.schema.json"
        schema = json.loads(schema_path.read_text())
        panel = schema.get("$defs", {}).get("Panel", {})
        comp = panel.get("properties", {}).get("composition_rule", {})
        enum_vals = comp.get("enum", [])
        assert "rule_of_thirds" in enum_vals
        assert "leading_lines" in enum_vals
        assert "symmetry" in enum_vals
        assert "golden_ratio" in enum_vals


class TestAxisBreak:
    """180° axis continuity lint."""

    def test_axis_flip_without_bridge_triggers_warning(self):
        shots = [
            {"id": "s1", "dramatic_function": "hook", "dsl": {"look_axis": "left"}},
            {"id": "s2", "dramatic_function": "action", "dsl": {"look_axis": "right"}},
        ]
        result = lint_composition_rules(shots)
        assert CODE_AXIS_BREAK in result["codes"]

    def test_axis_flip_with_bridge_no_warning(self):
        shots = [
            {"id": "s1", "dramatic_function": "hook", "dsl": {"look_axis": "left"}},
            {"id": "s2", "dramatic_function": "bridge", "dsl": {"look_axis": "right"}},
        ]
        result = lint_composition_rules(shots)
        assert CODE_AXIS_BREAK not in result["codes"]

    def test_same_axis_no_warning(self):
        shots = [
            {"id": "s1", "dramatic_function": "hook", "dsl": {"look_axis": "left"}},
            {"id": "s2", "dramatic_function": "action", "dsl": {"look_axis": "left"}},
        ]
        result = lint_composition_rules(shots)
        assert CODE_AXIS_BREAK not in result["codes"]

    def test_center_axis_never_triggers(self):
        shots = [
            {"id": "s1", "dsl": {"look_axis": "center"}},
            {"id": "s2", "dsl": {"look_axis": "left"}},
        ]
        result = lint_composition_rules(shots)
        assert CODE_AXIS_BREAK not in result["codes"]


class TestThirtyDegreeRule:
    """30-degree rule: same shot_size in adjacent shots."""

    def test_same_size_triggers_warning(self):
        shots = [
            {"id": "s1", "dramatic_function": "hook", "dsl": {"camera": {"shot_size": "medium"}}},
            {"id": "s2", "dramatic_function": "action", "dsl": {"camera": {"shot_size": "medium"}}},
        ]
        result = lint_composition_rules(shots)
        assert CODE_THIRTY_DEGREE_VIOLATION in result["codes"]

    def test_different_size_no_warning(self):
        shots = [
            {"id": "s1", "dsl": {"camera": {"shot_size": "wide"}}},
            {"id": "s2", "dsl": {"camera": {"shot_size": "close_up"}}},
        ]
        result = lint_composition_rules(shots)
        assert CODE_THIRTY_DEGREE_VIOLATION not in result["codes"]

    def test_insert_exempt(self):
        shots = [
            {"id": "s1", "dsl": {"camera": {"shot_size": "medium"}}},
            {"id": "s2", "dramatic_function": "insert", "dsl": {"camera": {"shot_size": "medium"}}},
        ]
        result = lint_composition_rules(shots)
        assert CODE_THIRTY_DEGREE_VIOLATION not in result["codes"]


class TestEyelineMatch:
    """Eyeline match continuity."""

    def test_eyeline_same_side_triggers_mismatch(self):
        shots = [
            {"id": "s1", "dsl": {"gaze_target": "left"}},
            {"id": "s2", "dsl": {"look_axis": "left"}},
        ]
        result = lint_composition_rules(shots)
        assert CODE_EYELINE_MISMATCH in result["codes"]

    def test_eyeline_opposite_side_no_mismatch(self):
        shots = [
            {"id": "s1", "dsl": {"gaze_target": "left"}},
            {"id": "s2", "dsl": {"look_axis": "right"}},
        ]
        result = lint_composition_rules(shots)
        assert CODE_EYELINE_MISMATCH not in result["codes"]


class TestSizeProgression:
    """Size progression flatness — 3 consecutive same size."""

    def test_three_same_size_triggers_warning(self):
        shots = [
            {"id": "s1", "dsl": {"camera": {"shot_size": "medium"}}},
            {"id": "s2", "dsl": {"camera": {"shot_size": "medium"}}},
            {"id": "s3", "dsl": {"camera": {"shot_size": "medium"}}},
        ]
        result = lint_composition_rules(shots)
        assert CODE_SIZE_PROGRESSION_FLAT in result["codes"]

    def test_varied_size_no_warning(self):
        shots = [
            {"id": "s1", "dsl": {"camera": {"shot_size": "wide"}}},
            {"id": "s2", "dsl": {"camera": {"shot_size": "medium"}}},
            {"id": "s3", "dsl": {"camera": {"shot_size": "close_up"}}},
        ]
        result = lint_composition_rules(shots)
        assert CODE_SIZE_PROGRESSION_FLAT not in result["codes"]


class TestCleanShots:
    """No issues when shots are well-formed."""

    def test_clean_shots_no_issues(self):
        shots = [
            {"id": "s1", "dsl": {"camera": {"shot_size": "wide"}, "look_axis": "left"}},
            {"id": "s2", "dsl": {"camera": {"shot_size": "medium"}, "look_axis": "left"}},
            {"id": "s3", "dsl": {"camera": {"shot_size": "close_up"}, "look_axis": "left"}},
        ]
        result = lint_composition_rules(shots)
        assert result["ok"] is True
        assert result["warning_count"] == 0

    def test_single_shot_no_issues(self):
        shots = [{"id": "s1", "dsl": {"camera": {"shot_size": "medium"}}}]
        result = lint_composition_rules(shots)
        assert result["ok"] is True
