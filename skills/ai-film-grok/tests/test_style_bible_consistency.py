"""Visual style-bible consistency gate: visual_bible 自动生成 (P2)."""

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

from assets.visual_bible import derive_style_bible_from_spec  # noqa: E402
from production_gates import (  # noqa: E402
    ProductionGateError,
    assert_style_bible_consistency,
    style_bible_consistency_report,
)


def _scenes(shots_meta):
    """Build spec['scenes'] from (shot_id, scene_id, shot_role) rows."""
    by_scene: dict[str, list[dict]] = {}
    for sid, scene, role in shots_meta:
        sh: dict = {"id": sid}
        if role is not None:
            sh["shot_role"] = role
        by_scene.setdefault(scene, []).append(sh)
    return [{"id": sc, "shots": shs} for sc, shs in by_scene.items()]


def _spec(shots_meta, cast_masters=None, **extra):
    spec = {"scenes": _scenes(shots_meta)}
    if cast_masters is not None:
        spec["cast_masters"] = cast_masters
    spec.update(extra)
    return spec


def _write_bible(root: Path, bible: dict | None) -> None:
    if bible is None:
        return
    (root / "style-bible.json").write_text(json.dumps(bible), encoding="utf-8")


class StyleBibleReportTests(unittest.TestCase):
    def test_no_visual_content_checked_false(self):
        rep = style_bible_consistency_report({})
        self.assertTrue(rep["ok"])
        self.assertFalse(rep["checked"])

    def test_root_none_checked_false(self):
        spec = _spec([("a", "s0", "hero"), ("b", "s0", "env")])
        rep = style_bible_consistency_report(spec, root=None)
        self.assertTrue(rep["ok"])
        self.assertFalse(rep["checked"])

    def test_bible_missing(self):
        spec = _spec([("a", "s0", "hero"), ("b", "s0", "env")])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            rep = style_bible_consistency_report(spec, root=root)
            self.assertFalse(rep["ok"], rep)
            self.assertIn("STYLE_BIBLE_MISSING", rep["codes"])

    def test_hero_cast_missing(self):
        spec = _spec([("a", "s0", "hero"), ("b", "s0", "env")])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write_bible(root, {"schema_version": 2, "state": "Draft", "locked": False,
                                "cast_masters": {"fufu": "canonical/fufu.png"}})
            rep = style_bible_consistency_report(spec, root=root)
            self.assertFalse(rep["ok"], rep)
            self.assertIn("STYLE_BIBLE_HERO_CAST_MISSING", rep["codes"])

    def test_lighting_mismatch(self):
        spec = _spec([("a", "s0", "hero"), ("b", "s0", "env")])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write_bible(root, {
                "schema_version": 2, "state": "Draft", "locked": False,
                "cast_masters": {"hero": "canonical/hero.png"},
                "lighting_timeline": [{"shot_id": "a"}],  # wrong length
            })
            rep = style_bible_consistency_report(spec, root=root)
            self.assertFalse(rep["ok"], rep)
            self.assertIn("STYLE_BIBLE_LIGHTING_MISMATCH", rep["codes"])

    def test_consistent_ok(self):
        spec = _spec([("a", "s0", "hero"), ("b", "s0", "env")])
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            _write_bible(root, {
                "schema_version": 2, "state": "Draft", "locked": False,
                "cast_masters": {"hero": "canonical/hero.png"},
                "lighting_timeline": [{"shot_id": "a"}, {"shot_id": "b"}],
            })
            rep = style_bible_consistency_report(spec, root=root)
            self.assertTrue(rep["ok"], rep)
            self.assertEqual(rep["codes"], [])

    def test_auto_derive_then_consistent(self):
        spec = _spec(
            [("a", "s0", "hero"), ("b", "s0", "env")],
            cast_masters={"hero": "canonical/hero.png"},
        )
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            bible = derive_style_bible_from_spec(spec, root)
            self.assertIn("hero", bible.get("cast_masters", {}))
            self.assertEqual(len(bible.get("lighting_timeline", [])), 2)
            rep = style_bible_consistency_report(spec, root=root)
            self.assertTrue(rep["ok"], rep)
            self.assertEqual(rep["codes"], [])


class StyleBibleAssertTests(unittest.TestCase):
    def _violating_spec(self, **extra):
        return _spec([("a", "s0", "hero"), ("b", "s0", "env")], **extra)

    def _root_without_bible(self):
        d = tempfile.mkdtemp()
        return Path(d)

    def test_soft_by_default(self):
        spec = self._violating_spec()
        root = self._root_without_bible()
        out = assert_style_bible_consistency(root=root, spec=spec)
        self.assertTrue(out["ok"])  # soft, never raises
        self.assertTrue(out["soft"])
        self.assertIn("STYLE_BIBLE_MISSING", out["codes"])

    def test_hard_under_strict(self):
        spec = self._violating_spec(style_bible_strict=True)
        root = self._root_without_bible()
        with self.assertRaises(ProductionGateError):
            assert_style_bible_consistency(root=root, spec=spec)

    def test_hard_under_adult_max_heat(self):
        spec = self._violating_spec(heat_scale="max")
        root = self._root_without_bible()
        with self.assertRaises(ProductionGateError):
            assert_style_bible_consistency(root=root, spec=spec)

    def test_escape_env(self):
        try:
            os.environ["AIFILM_SKIP_STYLE_BIBLE_GATE"] = "1"
            spec = self._violating_spec(style_bible_strict=True)
            root = self._root_without_bible()
            out = assert_style_bible_consistency(root=root, spec=spec)
            self.assertTrue(out["skipped"])
        finally:
            os.environ.pop("AIFILM_SKIP_STYLE_BIBLE_GATE", None)

    def test_force_skip(self):
        spec = self._violating_spec(style_bible_strict=True)
        root = self._root_without_bible()
        out = assert_style_bible_consistency(root=root, spec=spec, force=True)
        self.assertTrue(out["skipped"])


if __name__ == "__main__":
    unittest.main()
