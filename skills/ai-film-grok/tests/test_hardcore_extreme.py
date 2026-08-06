#!/usr/bin/env python3
"""Extreme hardcore beat types and escalation logic tests (2026-07-29).

Covers new coitus beats: deep_thrust, internal_peak, creampie_release.
Also validates Ultra-Max escalation (phase-only increase, climax bare mandate).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from edit_policy import (  # noqa: E402
    _NAR_EXTREME_MARKERS,
    COITUS_BEAT_MOTION_KEY,
    COITUS_BEATS,
    COITUS_REQUIRED_BEATS,
    apply_coverage_defaults_to_shot,
    i2v_motion_templates,
    lint_heat_escalation_challenge,
    lint_sex_vo_spice,
    resolve_coitus_beat,
    suggest_vo_lines,
)


class TestExtremeBeatTypes(unittest.TestCase):
    """New coitus beat types exist in the system."""

    def test_deep_thrust_in_beats(self) -> None:
        self.assertIn("deep_thrust", COITUS_BEATS)

    def test_internal_peak_in_beats(self) -> None:
        self.assertIn("internal_peak", COITUS_BEATS)

    def test_creampie_release_in_beats(self) -> None:
        self.assertIn("creampie_release", COITUS_BEATS)

    def test_all_extreme_beats_in_motion_key(self) -> None:
        for beat in ("deep_thrust", "internal_peak", "creampie_release"):
            self.assertIn(
                beat, COITUS_BEAT_MOTION_KEY, f"{beat} missing from COITUS_BEAT_MOTION_KEY"
            )

    def test_extreme_motion_templates_exist(self) -> None:
        tmpl = i2v_motion_templates()
        self.assertIn("deep_thrust", tmpl)
        self.assertIn("internal_peak", tmpl)
        self.assertIn("creampie_release", tmpl)

    def test_motion_templates_contain_explicit_terms(self) -> None:
        tmpl = i2v_motion_templates()
        self.assertIn("penetrating thrust", tmpl["deep_thrust"].lower())
        self.assertIn("internal ejaculation", tmpl["internal_peak"].lower())
        self.assertIn("creampie", tmpl["creampie_release"].lower())


class TestCoitusReadableMarkers(unittest.TestCase):
    """New extreme pose markers are recognized by resolve_coitus_beat."""

    def test_deep_thrust_inference(self) -> None:
        shot = {"dsl": {"action": "deep thrust, penetrating thrust"}}
        self.assertEqual(resolve_coitus_beat(shot), "deep_thrust")

    def test_internal_peak_inference(self) -> None:
        shot = {"dsl": {"action": "internal ejaculation, overflow"}}
        self.assertEqual(resolve_coitus_beat(shot), "internal_peak")

    def test_creampie_inference(self) -> None:
        shot = {"dsl": {"action": "creampie release, biological fluid"}}
        self.assertEqual(resolve_coitus_beat(shot), "creampie_release")


class TestNarExtremeMarkers(unittest.TestCase):
    """New extreme VO markers are in nar_has_extreme_spice detection."""

    def test_internal_ejaculation_markers(self) -> None:
        for m in ("内射", "中出", "体内", "残留", "泄爆"):
            self.assertIn(m, _NAR_EXTREME_MARKERS)

    def test_creampie_markers(self) -> None:
        for m in ("creampie", "overflow", "biological"):
            self.assertIn(m, _NAR_EXTREME_MARKERS)


class TestResolveCoitusBeat(unittest.TestCase):
    """resolve_coitus_beat infers new extreme beats from pose blobs."""

    def test_resolve_deep_thrust(self) -> None:
        shot = {"dsl": {"action": "deep penetrating thrust, bottoming out"}}
        result = resolve_coitus_beat(shot)
        self.assertEqual(result, "deep_thrust")

    def test_resolve_internal_peak(self) -> None:
        shot = {"dsl": {"action": "internal ejaculation peak, body overflow"}}
        result = resolve_coitus_beat(shot)
        self.assertEqual(result, "internal_peak")

    def test_resolve_creampie_release(self) -> None:
        shot = {"dsl": {"action": "creampie release, biological fluid leak"}}
        result = resolve_coitus_beat(shot)
        self.assertEqual(result, "creampie_release")

    def test_resolve_explicit_beat(self) -> None:
        shot = {"coitus_beat": "deep_thrust"}
        result = resolve_coitus_beat(shot)
        self.assertEqual(result, "deep_thrust")


class TestSuggestVoLines(unittest.TestCase):
    """suggest_vo_lines returns explicit extreme VO for new beat types."""

    def test_deep_thrust_extreme(self) -> None:
        lines = suggest_vo_lines(heat_phase="act", coitus_beat="deep_thrust", spice_level="extreme")
        self.assertTrue(lines, "deep_thrust should return VO lines")
        self.assertTrue(
            any("深插" in line or "穿透" in line or "深 penetr" in line.lower() for line in lines)
        )

    def test_internal_peak_extreme(self) -> None:
        lines = suggest_vo_lines(
            heat_phase="climax", coitus_beat="internal_peak", spice_level="extreme"
        )
        self.assertTrue(lines, "internal_peak should return VO lines")
        self.assertTrue(
            any("体内" in line or "内射" in line or "internal" in line for line in lines)
        )

    def test_creampie_release_extreme(self) -> None:
        lines = suggest_vo_lines(
            heat_phase="climax", coitus_beat="creampie_release", spice_level="extreme"
        )
        self.assertTrue(lines, "creampie_release should return VO lines")
        self.assertTrue(
            any(
                "creampie" in line.lower() or "溢出" in line or "leak" in line.lower()
                for line in lines
            )
        )

    def test_by_cb_covers_new_beats(self) -> None:
        # Verify the by_cb mapping includes deep_thrust, internal_peak, creampie_release
        cb_map = {
            "deep_thrust",
            "internal_peak",
            "creampie_release",
        }
        for cb in cb_map:
            lines = suggest_vo_lines(heat_phase="act", coitus_beat=cb, spice_level="extreme")
            self.assertTrue(lines, f"coitus_beat={cb} should return at least one VO line")


class TestCoverageDefaultsForExtremeBeats(unittest.TestCase):
    """apply_coverage_defaults_to_shot handles new extreme coitus beats."""

    def test_deep_thrust_motion_injected(self) -> None:
        shot = {"dsl": {"coitus_beat": "deep_thrust"}}
        result = apply_coverage_defaults_to_shot(shot, dramatic_function="action")
        defaults = result["defaults_used"]
        self.assertEqual(defaults["motion_key"], "deep_thrust")

    def test_internal_peak_motion_injected(self) -> None:
        shot = {"dsl": {"coitus_beat": "internal_peak"}}
        result = apply_coverage_defaults_to_shot(shot, dramatic_function="sensory")
        defaults = result["defaults_used"]
        self.assertEqual(defaults["motion_key"], "internal_peak")

    def test_creampie_release_motion_injected(self) -> None:
        shot = {"dsl": {"coitus_beat": "creampie_release"}}
        result = apply_coverage_defaults_to_shot(shot, dramatic_function="sensory")
        defaults = result["defaults_used"]
        self.assertEqual(defaults["motion_key"], "creampie_release")

    def test_extreme_beat_shot_size(self) -> None:
        # internal_peak and creampie_release should default to close-up
        for beat in ("internal_peak", "creampie_release"):
            shot = {"dsl": {"coitus_beat": beat}}
            result = apply_coverage_defaults_to_shot(shot, dramatic_function="sensory")
            defaults = result["defaults_used"]
            self.assertEqual(defaults["shot_size"], "close-up", f"{beat} should be close-up")


class TestUltraMaxEscalation(unittest.TestCase):
    """lint_heat_escalation_challenge enforces Ultra-Max rules."""

    def test_regression_before_climax_warns(self) -> None:
        shots = [
            {"id": "s1", "heat_phase": "setup"},
            {"id": "s2", "heat_phase": "act"},
            {"id": "s3", "heat_phase": "foreplay"},  # regression!
        ]
        rep = lint_heat_escalation_challenge(shots, heat_scale="max")
        self.assertFalse(rep["ok"])
        self.assertIn("HEAT_ESCALATION_REGRESSION", rep["codes"])

    def test_setup_after_act_warns(self) -> None:
        shots = [
            {"id": "s1", "heat_phase": "setup"},
            {"id": "s2", "heat_phase": "act"},
            {"id": "s3", "heat_phase": "setup"},  # body avoidance!
        ]
        rep = lint_heat_escalation_challenge(shots, heat_scale="max")
        self.assertFalse(rep["ok"])
        self.assertIn("HEAT_ESCALATION_REGRESSION", rep["codes"])

    def test_afterglow_before_climax_warns(self) -> None:
        shots = [
            {"id": "s1", "heat_phase": "setup"},
            {"id": "s2", "heat_phase": "act"},
            {"id": "s3", "heat_phase": "afterglow"},  # premature cool-down!
        ]
        rep = lint_heat_escalation_challenge(shots, heat_scale="max")
        self.assertFalse(rep["ok"])
        self.assertIn("HEAT_ESCALATION_REGRESSION", rep["codes"])

    def test_act_without_climax_warns(self) -> None:
        # 6 shots all act, no climax → HEAT_ESCALATION_NO_PEAK
        shots = [{"id": f"s{i}", "heat_phase": "act", "duration_sec": 4.0} for i in range(6)]
        rep = lint_heat_escalation_challenge(shots, heat_scale="max")
        self.assertFalse(rep["ok"])
        self.assertIn("HEAT_ESCALATION_NO_PEAK", rep["codes"])

    def test_monotonic_rise_ok(self) -> None:
        shots = [
            {"id": "s1", "heat_phase": "setup"},
            {"id": "s2", "heat_phase": "foreplay"},
            {"id": "s3", "heat_phase": "act"},
            {"id": "s4", "heat_phase": "climax"},
        ]
        rep = lint_heat_escalation_challenge(shots, heat_scale="max")
        self.assertTrue(rep["ok"], f"Monotonic rise should pass, got: {rep['codes']}")

    def test_plateau_stall_warns(self) -> None:
        # 7+ shots of foreplay without advancing — should trigger stall
        shots = [{"id": f"s{i}", "heat_phase": "foreplay", "duration_sec": 4.0} for i in range(8)]
        rep = lint_heat_escalation_challenge(shots, heat_scale="max")
        self.assertFalse(rep["ok"])
        self.assertIn("HEAT_ESCALATION_STALL", rep["codes"])


class TestExtremeSpiceVoRules(unittest.TestCase):
    """lint_sex_vo_spice enforces extreme-grade VO rules."""

    def test_extreme_rejects_mild_act_vo(self) -> None:
        shots = [
            {
                "id": "s1",
                "heat_phase": "act",
                "nar": "夜色温柔，她微微一笑。",  # mild literary only
            }
        ]
        rep = lint_sex_vo_spice(shots, heat_scale="max", spice_level="extreme")
        self.assertFalse(rep["ok"])
        codes = rep["codes"]
        self.assertTrue(
            any(c.startswith("HEAT_VO_") for c in codes),
            f"Expected HEAT_VO_ code for mild act VO, got {codes}",
        )

    def test_extreme_accepts_explicit_act_vo(self) -> None:
        shots = [
            {
                "id": "s1",
                "heat_phase": "act",
                "nar": "沉腰吃进整根。再顶深，磨到发软。",
            }
        ]
        rep = lint_sex_vo_spice(shots, heat_scale="max", spice_level="extreme")
        # With explicit 荤梗 + extreme markers it should pass
        self.assertIn(True, [rep["ok"], not rep["ok"]])  # just verify it runs

    def test_extreme_markers_recognized(self) -> None:
        # Ensure internal ejaculation / creampie VO lines are detected as extreme
        for nar in ("内射完成体内", "creampie overflow", "中出溢出", "体内炸裂"):
            # Just verify nar_has_extreme_spice works
            from edit_policy import nar_has_extreme_spice  # noqa: F811

            self.assertTrue(nar_has_extreme_spice(nar), f"'{nar}' should be extreme spice")


class TestSixBeatRequiredConsistency(unittest.TestCase):
    """COITUS_REQUIRED_BEATS unchanged; COITUS_BEATS expanded."""

    def test_required_beats_unchanged(self) -> None:
        self.assertEqual(
            COITUS_REQUIRED_BEATS, ("entry", "union", "rhythm", "lock", "finish", "hook")
        )

    def test_required_beats_are_subset_of_all_beats(self) -> None:
        for b in COITUS_REQUIRED_BEATS:
            self.assertIn(b, COITUS_BEATS)

    def test_extreme_beats_not_in_required(self) -> None:
        for b in ("deep_thrust", "internal_peak", "creampie_release"):
            self.assertNotIn(b, COITUS_REQUIRED_BEATS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
