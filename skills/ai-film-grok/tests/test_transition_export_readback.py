"""Controlled transition export read-back gate: HF 转场 export read-back 全量 (P2).

Reads back built transition_ops and verifies full seam coverage + policy
consistency with the declared transition_intents/transition_styles.
"""

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
    assert_transition_export_readback,
    transition_export_readback_report,
)


def _scenes(shots_meta):
    """Build spec['scenes'] from (shot_id, scene_id, chain_mode, df, role) rows."""
    by_scene: dict[str, list[dict]] = {}
    for sid, scene, chain_mode, df, role in shots_meta:
        sh: dict = {"id": sid}
        if chain_mode is not None:
            sh["dsl"] = {"chain_mode": chain_mode}
        if df is not None:
            sh["dramatic_function"] = df
        if role is not None:
            sh["role"] = role
        by_scene.setdefault(scene, []).append(sh)
    return [{"id": sc, "shots": shs} for sc, shs in by_scene.items()]


def _spec(shots_meta, intents, styles=None, ops=None, **extra):
    spec = {"scenes": _scenes(shots_meta), "transition_intents": intents}
    if styles is not None:
        spec["transition_styles"] = styles
    if ops is not None:
        spec["transition_ops"] = ops
    spec.update(extra)
    return spec


def _op(base, style, dur=0.0, overlay="none"):
    return {
        "join_index": 0,
        "picture": {
            "base": base,
            "style": style,
            "duration_sec": dur,
            "hyperframes_overlay": overlay,
        },
    }


def _ops(*pics):
    out = []
    for i, pic in enumerate(pics):
        if len(pic) == 2:
            base, style = pic
            dur, overlay = 0.0, "none"
        elif len(pic) == 3:
            base, style, dur = pic
            overlay = "none"
        else:
            base, style, dur, overlay = pic
        out.append({**_op(base, style, dur, overlay), "join_index": i})
    return out


class TransitionReadbackReportTests(unittest.TestCase):
    def test_no_declared_seams_checked_false(self):
        rep = transition_export_readback_report({})
        self.assertTrue(rep["ok"])
        self.assertFalse(rep["checked"])

    def test_ops_missing_when_seams_declared(self):
        # declares 1 seam but no transition_ops → coverage gap
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s0", None, None, None)],
            intents=["soft"],
        )
        rep = transition_export_readback_report(spec)
        self.assertFalse(rep["ok"], rep)
        self.assertTrue(rep["checked"])
        self.assertIn("EXPORT_READBACK_NO_OPS", rep["codes"])
        self.assertEqual(rep["seam_count"], 1)
        self.assertEqual(rep["ops_count"], 0)

    def test_op_count_mismatch(self):
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s0", None, None, None), ("c", "s0", None, None, None)],
            intents=["soft", "soft"],
            ops=_ops(("xfade", "fade")),
        )
        rep = transition_export_readback_report(spec)
        self.assertFalse(rep["ok"], rep)
        self.assertIn("EXPORT_READBACK_OP_COUNT_MISMATCH", rep["codes"])
        self.assertEqual(rep["seam_count"], 2)

    def test_continue_seam_softened_in_ops(self):
        # incoming shot b has chain_mode=continue; op is xfade → not hard
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s0", "continue", None, None)],
            intents=["hard"],
            ops=_ops(("xfade", "none")),
        )
        rep = transition_export_readback_report(spec)
        self.assertFalse(rep["ok"], rep)
        self.assertIn("EXPORT_READBACK_CONTINUE_NOT_HARD", rep["codes"])

    def test_continue_seam_hard_ok(self):
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s0", "continue", None, None)],
            intents=["hard"],
            ops=_ops(("hard_cut", "none", 0.0, "none")),
        )
        rep = transition_export_readback_report(spec)
        self.assertTrue(rep["ok"], rep)
        self.assertEqual(rep["codes"], [])

    def test_soft_xfade_ok(self):
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, None, None)],
            intents=["soft"],
            styles=["fade"],
            ops=_ops(("xfade", "fade")),
        )
        rep = transition_export_readback_report(spec)
        self.assertTrue(rep["ok"], rep)
        self.assertEqual(rep["codes"], [])

    def test_soft_style_drift(self):
        # declared fade but built dissolve → drift
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, None, None)],
            intents=["soft"],
            styles=["fade"],
            ops=_ops(("xfade", "dissolve")),
        )
        rep = transition_export_readback_report(spec)
        self.assertFalse(rep["ok"], rep)
        self.assertIn("EXPORT_READBACK_STYLE_DRIFT", rep["codes"])

    def test_soft_not_xfade(self):
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, None, None)],
            intents=["soft"],
            styles=["fade"],
            ops=_ops(("hard_cut", "none")),
        )
        rep = transition_export_readback_report(spec)
        self.assertFalse(rep["ok"], rep)
        self.assertIn("EXPORT_READBACK_SOFT_NOT_XFADE", rep["codes"])

    def test_hard_seam_not_cut(self):
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, None, None)],
            intents=["hard"],
            ops=_ops(("xfade", "none")),
        )
        rep = transition_export_readback_report(spec)
        self.assertFalse(rep["ok"], rep)
        self.assertIn("EXPORT_READBACK_HARD_NOT_CUT", rep["codes"])

    def test_scene_cut_flashy_style(self):
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, None, None)],
            intents=["soft"],
            styles=["whip"],
            ops=_ops(("xfade", "whip")),
        )
        rep = transition_export_readback_report(spec)
        self.assertFalse(rep["ok"], rep)
        self.assertIn("EXPORT_READBACK_FLASHY_STYLE", rep["codes"])

    def test_chapter_transition_soft_fade_ok(self):
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, "chapter_transition", None)],
            intents=["soft"],
            styles=["fade"],
            ops=_ops(("xfade", "fade")),
        )
        rep = transition_export_readback_report(spec)
        self.assertTrue(rep["ok"], rep)
        self.assertEqual(rep["codes"], [])

    def test_chapter_transition_hard_bad(self):
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, "chapter_transition", None)],
            intents=["soft"],
            styles=["fade"],
            ops=_ops(("hard_cut", "none")),
        )
        rep = transition_export_readback_report(spec)
        self.assertFalse(rep["ok"], rep)
        self.assertIn("EXPORT_READBACK_PARAGRAPH_BAD", rep["codes"])

    def test_intro_relaxed_allows_flashy(self):
        # role intro → relax, even flashy style passes
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, None, "intro")],
            intents=["soft"],
            styles=["whip"],
            ops=_ops(("xfade", "whip")),
        )
        rep = transition_export_readback_report(spec)
        self.assertTrue(rep["ok"], rep)
        self.assertEqual(rep["codes"], [])


class TransitionReadbackAssertTests(unittest.TestCase):
    def _violating_spec(self, **extra):
        return _spec(
            [("a", "s0", None, None, None), ("b", "s0", "continue", None, None)],
            intents=["hard"],
            ops=_ops(("xfade", "none")),
            **extra,
        )

    def test_hard_by_default(self):
        with self.assertRaises(ProductionGateError) as ctx:
            assert_transition_export_readback(spec=self._violating_spec())
        self.assertIn("EXPORT_READBACK_CONTINUE_NOT_HARD", str(ctx.exception))

    def test_hard_under_strict(self):
        with self.assertRaises(ProductionGateError):
            assert_transition_export_readback(
                spec=self._violating_spec(transition_policy_strict=True)
            )

    def test_hard_under_adult_max_heat(self):
        with self.assertRaises(ProductionGateError):
            assert_transition_export_readback(spec=self._violating_spec(heat_scale="max"))

    def test_soft_when_opt_out(self):
        out = assert_transition_export_readback(
            spec=self._violating_spec(transition_policy_soft=True)
        )
        self.assertTrue(out["ok"])
        self.assertTrue(out["soft"])
        self.assertIn("EXPORT_READBACK_CONTINUE_NOT_HARD", out["codes"])

    def test_escape_env(self):
        try:
            os.environ["AIFILM_SKIP_TRANSITION_READBACK_GATE"] = "1"
            out = assert_transition_export_readback(
                spec=self._violating_spec(transition_policy_strict=True)
            )
            self.assertTrue(out["skipped"])
        finally:
            os.environ.pop("AIFILM_SKIP_TRANSITION_READBACK_GATE", None)

    def test_force_skip(self):
        out = assert_transition_export_readback(
            spec=self._violating_spec(transition_policy_strict=True), force=True
        )
        self.assertTrue(out["skipped"])

    def test_from_root_spec_file(self):
        spec = self._violating_spec()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaises(ProductionGateError):
                assert_transition_export_readback(root=str(root))


if __name__ == "__main__":
    unittest.main()
