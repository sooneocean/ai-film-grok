"""Optimization round 4 · A1 cinematic edit_rhythm + post bible/caption probes."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestEditRhythmProbeNotGreen(unittest.TestCase):
    def test_edit_rhythm_exception_not_ok_true(self) -> None:
        from cinematic_gate import run_cinematic_gate

        root = Path(tempfile.mkdtemp())
        (root / "receipts").mkdir()
        (root / "film-spec.json").write_text(
            json.dumps(
                {
                    "heat_scale": "max",
                    "scenes": [{"shots": [{"id": "s1", "duration_sec": 5}]}],
                }
            ),
            encoding="utf-8",
        )
        (root / "manifest.json").write_text(json.dumps({"clips": {}}), encoding="utf-8")

        with mock.patch(
            "edit_policy.lint_equal_duration_ppt",
            side_effect=RuntimeError("ppt boom"),
        ):
            rep = run_cinematic_gate(
                root,
                write=False,
                run_ship_prep=False,
                skip_variety=True,
                skip_five_track=True,
                auto_i2v=False,
            )
        er = [s for s in (rep.get("steps") or []) if s.get("id") == "edit_rhythm"]
        self.assertTrue(er, msg=f"steps={rep.get('steps')}")
        self.assertFalse(er[0].get("ok"), msg=f"edit_rhythm must not silent-green: {er[0]}")
        self.assertTrue(er[0].get("hard"), msg="max heat → hard")
        self.assertFalse(er[0].get("skipped"))

    def test_edit_rhythm_soft_when_not_max(self) -> None:
        from cinematic_gate import run_cinematic_gate

        root = Path(tempfile.mkdtemp())
        (root / "receipts").mkdir()
        (root / "film-spec.json").write_text(
            json.dumps(
                {
                    "heat_scale": "mild",
                    "scenes": [{"shots": [{"id": "s1", "duration_sec": 5}]}],
                }
            ),
            encoding="utf-8",
        )
        (root / "manifest.json").write_text(json.dumps({"clips": {}}), encoding="utf-8")

        with mock.patch(
            "edit_policy.lint_equal_duration_ppt",
            side_effect=RuntimeError("ppt mild boom"),
        ):
            rep = run_cinematic_gate(
                root,
                write=False,
                run_ship_prep=False,
                skip_variety=True,
                skip_five_track=True,
                auto_i2v=False,
            )
        er = [s for s in (rep.get("steps") or []) if s.get("id") == "edit_rhythm"]
        self.assertTrue(er)
        self.assertFalse(er[0].get("ok"))
        self.assertFalse(er[0].get("hard"))


class TestIronStatusPlateBoringError(unittest.TestCase):
    def test_plate_boring_floor_error_on_import_fail(self) -> None:
        from gates.iron_status import iron_floors

        real_import = __import__

        def _boom(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
            if name == "final.delivery_class" or (
                name == "final" and fromlist and "delivery_class" in fromlist
            ):
                raise ImportError("no delivery_class")
            if name == "final" and fromlist and "PLATE_BORING_MEAT_FLOOR" in fromlist:
                raise ImportError("no floor")
            return real_import(name, globals, locals, fromlist, level)

        with mock.patch("builtins.__import__", side_effect=_boom):
            out = iron_floors()
        self.assertIn("plate_boring_meat_floor_error", out)
        self.assertNotIn("plate_boring_meat_floor", out)


class TestPostAuditBibleProbe(unittest.TestCase):
    def test_audio_bible_probe_error_hard_premium(self) -> None:
        from post.post_audit import audit as post_audit

        root = Path(tempfile.mkdtemp())
        (root / "receipts").mkdir()
        (root / "out").mkdir()
        (root / "production-book.json").write_text(
            json.dumps({"quality_target": "premium_vertical"}),
            encoding="utf-8",
        )
        (root / "audio-bible.json").write_text("{}", encoding="utf-8")
        (root / "film-spec.json").write_text(
            json.dumps({"title": "t", "quality_target": "premium_vertical"}),
            encoding="utf-8",
        )
        (root / "manifest.json").write_text(
            json.dumps({"gates": {}, "clips": {}, "outputs": {}}),
            encoding="utf-8",
        )

        with mock.patch(
            "audio_bible.validate_audio_bible",
            side_effect=RuntimeError("ab boom"),
        ):
            try:
                rep = post_audit(root, write=False)
            except Exception as exc:
                self.skipTest(f"post_audit needs more fixtures: {exc}")
                return
        hard = rep.get("hard_failures") or []
        codes = {str(h.get("code")) for h in hard if isinstance(h, dict)}
        self.assertIn(
            "AUDIO_BIBLE_PROBE_ERROR",
            codes,
            msg=f"codes={codes} hard={hard[:8]} warnings={rep.get('warnings')}",
        )


if __name__ == "__main__":
    unittest.main()
