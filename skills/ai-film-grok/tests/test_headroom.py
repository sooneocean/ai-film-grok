"""Headroom / anti-crop gate: timeline lead-in protection (P1)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

pytestmark = pytest.mark.hotpath

from production_gates import (  # noqa: E402
    ProductionGateError,
    assert_headroom_protected,
    headroom_report,
)


def _spec(scenes=None, shots=None, **extra):
    spec = {}
    if scenes is not None:
        spec["scenes"] = scenes
    if shots is not None:
        spec["shots"] = shots
    spec.update(extra)
    return spec


def _shot(sid, dur):
    return {"id": sid, "duration_sec": dur}


class HeadroomReportTests(unittest.TestCase):
    def test_empty_spec_ok(self):
        rep = headroom_report({})
        self.assertTrue(rep["ok"])
        self.assertTrue(rep["checked"])

    def test_healthy_spec_ok(self):
        spec = _spec(
            scenes=[
                {"shots": [_shot("s1", 4.0), _shot("s2", 3.0)]},
                {"shots": [_shot("s3", 5.0)]},
            ]
        )
        rep = headroom_report(spec)
        self.assertTrue(rep["ok"], rep)
        self.assertEqual(rep["codes"], [])

    def test_short_shot_flagged(self):
        spec = _spec(scenes=[{"shots": [_shot("s1", 4.0), _shot("s2", 1.0)]}])
        rep = headroom_report(spec)
        self.assertFalse(rep["ok"])
        self.assertIn("HEADROOM_SHOT_TOO_SHORT", rep["codes"])

    def test_scene_opening_too_short_flagged(self):
        # 2.5s passes the 2.0s floor but fails the 3.5s lead-in floor for openers.
        spec = _spec(scenes=[{"shots": [_shot("s1", 2.5), _shot("s2", 4.0)]}])
        rep = headroom_report(spec)
        self.assertIn("HEADROOM_FIRST_SHOT_TOO_SHORT", rep["codes"])
        self.assertNotIn("HEADROOM_SHOT_TOO_SHORT", rep["codes"])

    def test_toplevel_shots_flagged(self):
        spec = _spec(shots=[_shot("t1", 1.5), _shot("t2", 4.0)])
        rep = headroom_report(spec)
        self.assertIn("HEADROOM_SHOT_TOO_SHORT", rep["codes"])

    def test_missing_duration_ignored(self):
        # No duration_sec → can't judge, should not flag.
        spec = _spec(scenes=[{"shots": [{"id": "s1"}, {"id": "s2", "duration_sec": 1.0}]}])
        rep = headroom_report(spec)
        self.assertIn("HEADROOM_SHOT_TOO_SHORT", rep["codes"])
        self.assertEqual(len(rep["issues"]), 1)


class HeadroomAssertTests(unittest.TestCase):
    def test_soft_by_default(self):
        spec = _spec(scenes=[{"shots": [_shot("s1", 1.0)]}])
        out = assert_headroom_protected(spec=spec)
        self.assertTrue(out["ok"])  # soft, never raises
        self.assertTrue(out["soft"])
        self.assertIn("HEADROOM_SHOT_TOO_SHORT", out["codes"])

    def test_hard_under_strict(self):
        spec = _spec(scenes=[{"shots": [_shot("s1", 1.0)]}], headroom_strict=True)
        with self.assertRaises(ProductionGateError):
            assert_headroom_protected(spec=spec)

    def test_hard_under_adult_max_heat(self):
        spec = _spec(
            scenes=[{"shots": [_shot("s1", 1.0)]}], heat_scale="max"
        )
        with self.assertRaises(ProductionGateError):
            assert_headroom_protected(spec=spec)

    def test_escape_env(self):
        spec = _spec(scenes=[{"shots": [_shot("s1", 1.0)]}], headroom_strict=True)
        try:
            os.environ["AIFILM_SKIP_HEADROOM_GATE"] = "1"
            out = assert_headroom_protected(spec=spec)
            self.assertTrue(out["skipped"])
        finally:
            os.environ.pop("AIFILM_SKIP_HEADROOM_GATE", None)

    def test_force_skip(self):
        spec = _spec(scenes=[{"shots": [_shot("s1", 1.0)]}], headroom_strict=True)
        out = assert_headroom_protected(spec=spec, force=True)
        self.assertTrue(out["skipped"])

    def test_from_root_spec_file(self):
        spec = _spec(scenes=[{"shots": [_shot("s1", 1.0)]}])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "film-spec.json").write_text(
                json.dumps(spec), encoding="utf-8"
            )
            out = assert_headroom_protected(root=str(root))
            self.assertTrue(out["soft"])
            self.assertIn("HEADROOM_SHOT_TOO_SHORT", out["codes"])


if __name__ == "__main__":
    unittest.main()
