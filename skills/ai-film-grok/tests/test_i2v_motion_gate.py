#!/usr/bin/env python3
"""High-motion I2V gate (P0 · 2026-07-27): meat≥20 normal≥18; no KB plate."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from i2v_motion_gate import (  # noqa: E402
    CODE_FORBIDDEN_SOURCE,
    CODE_MEAT_MEAN_LOW,
    CODE_NORMAL_MEAN_LOW,
    MEAN_MEAT_FLOOR,
    MEAN_MEAT_TARGET,
    MEAN_NORMAL_FLOOR,
    build_high_motion_audit,
    build_i2v_final_gate,
    evaluate_shot_motion,
    floor_for_tier,
    lint_still_source_policy,
    motion_tier_for_phase,
    still_source_allows_full_cast,
    write_motion_gate_receipts,
)


class MotionFloorConstants(unittest.TestCase):
    def test_floors_match_hard_defaults(self) -> None:
        self.assertEqual(MEAN_NORMAL_FLOOR, 18.0)
        self.assertEqual(MEAN_MEAT_FLOOR, 20.0)
        self.assertEqual(MEAN_MEAT_TARGET, 24.0)
        self.assertEqual(floor_for_tier("meat"), 20.0)
        self.assertEqual(floor_for_tier("normal"), 18.0)

    def test_tier_from_phase(self) -> None:
        self.assertEqual(motion_tier_for_phase("act"), "meat")
        self.assertEqual(motion_tier_for_phase("climax"), "meat")
        self.assertEqual(motion_tier_for_phase("setup"), "normal")
        self.assertEqual(motion_tier_for_phase("foreplay"), "normal")


class EvaluateShotMotion(unittest.TestCase):
    def test_meat_below_20_fails(self) -> None:
        r = evaluate_shot_motion(19.5, heat_phase="act", shot_id="a1")
        self.assertFalse(r["ok"])
        self.assertEqual(r["tier"], "meat")
        self.assertIn(CODE_MEAT_MEAN_LOW, r["codes"])
        self.assertEqual(r["floor"], 20.0)

    def test_meat_at_20_ok(self) -> None:
        r = evaluate_shot_motion(20.0, heat_phase="climax", shot_id="c1")
        self.assertTrue(r["ok"])
        self.assertNotIn(CODE_MEAT_MEAN_LOW, r["codes"])

    def test_normal_below_18_fails(self) -> None:
        r = evaluate_shot_motion(17.0, heat_phase="setup", shot_id="s1")
        self.assertFalse(r["ok"])
        self.assertIn(CODE_NORMAL_MEAN_LOW, r["codes"])

    def test_normal_at_18_ok(self) -> None:
        r = evaluate_shot_motion(18.0, heat_phase="bridge", shot_id="b1")
        self.assertTrue(r["ok"])

    def test_ken_burns_forbidden(self) -> None:
        r = evaluate_shot_motion(30.0, heat_phase="act", source="ken_burns", shot_id="kb")
        self.assertFalse(r["ok"])
        self.assertIn(CODE_FORBIDDEN_SOURCE, r["codes"])


class AuditAndFinalGate(unittest.TestCase):
    def test_audit_meat_fail_blocks_ok(self) -> None:
        audit = build_high_motion_audit(
            [
                {"id": "s1", "heat_phase": "setup", "mean": 19.0},
                {"id": "a1", "heat_phase": "act", "mean": 12.0},  # weak meat
            ]
        )
        self.assertFalse(audit["ok"])
        self.assertIn(CODE_MEAT_MEAN_LOW, audit["codes"])
        gate = build_i2v_final_gate(audit, raw_complete=True, style_ok=True)
        self.assertFalse(gate["ok"])
        self.assertFalse(gate["desktop_final_allowed"])

    def test_audit_pass_and_gate_ok(self) -> None:
        audit = build_high_motion_audit(
            [
                {"id": "s1", "heat_phase": "setup", "mean_absdiff": 18.5},
                {"id": "a1", "heat_phase": "act", "mean_absdiff": 22.0},
                {"id": "c1", "heat_phase": "climax", "mean_absdiff": 24.0},
            ]
        )
        self.assertTrue(audit["ok"], audit)
        gate = build_i2v_final_gate(
            audit, raw_complete=True, kb_fallback=False, style_ok=True, shot_count=3, raw_ok_count=3
        )
        self.assertTrue(gate["ok"])
        self.assertTrue(gate["desktop_final_allowed"])

    def test_kb_fallback_blocks_final(self) -> None:
        audit = build_high_motion_audit(
            [{"id": "a1", "heat_phase": "act", "mean": 25.0}]
        )
        gate = build_i2v_final_gate(audit, kb_fallback=True)
        self.assertFalse(gate["ok"])

    def test_write_receipts(self) -> None:
        audit = build_high_motion_audit(
            [{"id": "a1", "heat_phase": "act", "mean": 21.0}]
        )
        gate = build_i2v_final_gate(audit)
        with tempfile.TemporaryDirectory() as td:
            paths = write_motion_gate_receipts(td, audit, gate)
            self.assertTrue(Path(paths["audit"]).is_file())
            self.assertTrue(Path(paths["gate"]).is_file())


class StillSourceNoRedress(unittest.TestCase):
    def test_full_cast_forbidden_when_undressed(self) -> None:
        self.assertFalse(still_source_allows_full_cast("undressed"))
        self.assertFalse(still_source_allows_full_cast("bare"))
        self.assertTrue(still_source_allows_full_cast("full"))

    def test_lint_flags_full_cast_after_undress(self) -> None:
        rep = lint_still_source_policy(
            [
                {
                    "id": "a1",
                    "wardrobe_state": "bare",
                    "still_source": "cast_master",
                }
            ]
        )
        self.assertFalse(rep["ok"])
        self.assertIn("STILL_SOURCE_FULL_CAST_RE_DRESS", rep["codes"])

    def test_undress_anchor_ok(self) -> None:
        rep = lint_still_source_policy(
            [
                {
                    "id": "a1",
                    "wardrobe_state": "bare",
                    "still_source": "undress-anchor",
                }
            ]
        )
        self.assertTrue(rep["ok"])


if __name__ == "__main__":
    unittest.main()
