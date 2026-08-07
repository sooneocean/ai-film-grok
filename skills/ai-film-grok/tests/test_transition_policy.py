"""Controlled transition-policy gate: HF 转场受控策略全量 (P2)."""

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
    assert_transition_policy,
    transition_policy_report,
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


def _spec(shots_meta, intents, styles=None, **extra):
    spec = {"scenes": _scenes(shots_meta), "transition_intents": intents}
    if styles is not None:
        spec["transition_styles"] = styles
    spec.update(extra)
    return spec


class TransitionPolicyReportTests(unittest.TestCase):
    def test_empty_spec_ok(self):
        rep = transition_policy_report({})
        self.assertTrue(rep["ok"])
        self.assertFalse(rep["checked"])

    def test_no_intents_skipped(self):
        rep = transition_policy_report({"scenes": [{"shots": [{"id": "a"}, {"id": "b"}]}]})
        self.assertTrue(rep["ok"])
        self.assertFalse(rep["checked"])

    def test_continue_seam_must_be_hard(self):
        # shot b has chain_mode=continue; intent soft → violation
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s0", "continue", None, None)],
            intents=["soft"],
        )
        rep = transition_policy_report(spec)
        self.assertFalse(rep["ok"], rep)
        self.assertIn("HF_TRANSITION_CONTINUE_NOT_HARD", rep["codes"])

    def test_continue_seam_hard_ok(self):
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s0", "continue", None, None)],
            intents=["hard"],
        )
        rep = transition_policy_report(spec)
        self.assertTrue(rep["ok"], rep)
        self.assertEqual(rep["codes"], [])

    def test_paragraph_transition_soft_fade_ok(self):
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, "chapter_transition", None)],
            intents=["soft"],
            styles=["fade"],
        )
        rep = transition_policy_report(spec)
        self.assertTrue(rep["ok"], rep)
        self.assertEqual(rep["codes"], [])

    def test_paragraph_transition_hard_bad(self):
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, "chapter_transition", None)],
            intents=["hard"],
        )
        rep = transition_policy_report(spec)
        self.assertFalse(rep["ok"], rep)
        self.assertIn("HF_TRANSITION_PARAGRAPH_BAD", rep["codes"])

    def test_paragraph_transition_flashy_style_bad(self):
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, "chapter_transition", None)],
            intents=["soft"],
            styles=["whip"],
        )
        rep = transition_policy_report(spec)
        self.assertFalse(rep["ok"], rep)
        self.assertIn("HF_TRANSITION_PARAGRAPH_BAD", rep["codes"])

    def test_scene_cut_flashy_style_bad(self):
        # cross_scene (s0→s1); style whip forbidden on scene cut
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, None, None)],
            intents=["soft"],
            styles=["whip"],
        )
        rep = transition_policy_report(spec)
        self.assertFalse(rep["ok"], rep)
        self.assertIn("HF_TRANSITION_SCENE_FLASHY_STYLE", rep["codes"])

    def test_scene_cut_normal_fade_ok(self):
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, None, None)],
            intents=["soft"],
            styles=["fade"],
        )
        rep = transition_policy_report(spec)
        self.assertTrue(rep["ok"], rep)
        self.assertEqual(rep["codes"], [])

    def test_intro_outro_relaxed_all(self):
        # role intro → allow-all even with flashy style
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, None, "intro")],
            intents=["soft"],
            styles=["whip"],
        )
        rep = transition_policy_report(spec)
        self.assertTrue(rep["ok"], rep)
        self.assertEqual(rep["codes"], [])


class TransitionPolicyAssertTests(unittest.TestCase):
    def _violating_spec(self, **extra):
        return _spec(
            [("a", "s0", None, None, None), ("b", "s0", "continue", None, None)],
            intents=["soft"],
            **extra,
        )

    def test_hard_by_default(self):
        """Continue soft-intent is always hard (接戏铁律 + default hard policy)."""
        with self.assertRaises(ProductionGateError) as ctx:
            assert_transition_policy(spec=self._violating_spec())
        self.assertIn("HF_TRANSITION_CONTINUE_NOT_HARD", str(ctx.exception))

    def test_hard_under_strict(self):
        with self.assertRaises(ProductionGateError):
            assert_transition_policy(spec=self._violating_spec(transition_policy_strict=True))

    def test_hard_under_adult_max_heat(self):
        with self.assertRaises(ProductionGateError):
            assert_transition_policy(spec=self._violating_spec(heat_scale="max"))

    def test_continue_hard_even_when_soft_opt_out(self):
        with self.assertRaises(ProductionGateError):
            assert_transition_policy(spec=self._violating_spec(transition_policy_soft=True))

    def test_non_continue_soft_when_opt_out(self):
        # scene whip is non-continue; soft opt-out → advisory only
        spec = _spec(
            [("a", "s0", None, None, None), ("b", "s1", None, None, None)],
            intents=["soft"],
            styles=["whip"],
            transition_policy_soft=True,
        )
        out = assert_transition_policy(spec=spec)
        self.assertTrue(out["ok"])
        self.assertTrue(out["soft"])
        self.assertIn("HF_TRANSITION_SCENE_FLASHY_STYLE", out["codes"])

    def test_escape_env(self):
        try:
            os.environ["AIFILM_SKIP_TRANSITION_POLICY_GATE"] = "1"
            out = assert_transition_policy(
                spec=self._violating_spec(transition_policy_strict=True)
            )
            self.assertTrue(out["skipped"])
        finally:
            os.environ.pop("AIFILM_SKIP_TRANSITION_POLICY_GATE", None)

    def test_force_skip(self):
        out = assert_transition_policy(
            spec=self._violating_spec(transition_policy_strict=True), force=True
        )
        self.assertTrue(out["skipped"])

    def test_from_root_spec_file(self):
        spec = self._violating_spec()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "film-spec.json").write_text(json.dumps(spec), encoding="utf-8")
            with self.assertRaises(ProductionGateError):
                assert_transition_policy(root=str(root))


class TransitionSoftSoupTests(unittest.TestCase):
    def test_soft_soup_detected(self):
        # 4 soft joins all fade under auto fluency (max 3) → soup on 4th
        rows = [(f"s{i}", "sc0", None, None, None) for i in range(5)]
        spec = _spec(rows, intents=["soft"] * 4, styles=["fade"] * 4)
        rep = transition_policy_report(spec)
        self.assertFalse(rep["ok"], rep)
        self.assertIn("HF_TRANSITION_SOFT_SOUP", rep["codes"])

    def test_rotated_soft_styles_ok(self):
        rows = [(f"s{i}", "sc0", None, None, None) for i in range(5)]
        styles = ["fade", "dissolve", "smoothleft", "hblur"]
        spec = _spec(rows, intents=["soft"] * 4, styles=styles)
        rep = transition_policy_report(spec)
        self.assertTrue(rep["ok"], rep)
        self.assertNotIn("HF_TRANSITION_SOFT_SOUP", rep["codes"])

    def test_punchy_max_two(self):
        rows = [(f"s{i}", "sc0", None, None, None) for i in range(4)]
        spec = _spec(
            rows,
            intents=["soft"] * 3,
            styles=["dissolve"] * 3,
            transition_fluency="punchy",
        )
        rep = transition_policy_report(spec)
        self.assertIn("HF_TRANSITION_SOFT_SOUP", rep["codes"])


if __name__ == "__main__":
    unittest.main()
