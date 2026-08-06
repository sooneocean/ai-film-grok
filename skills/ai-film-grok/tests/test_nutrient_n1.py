"""Wave N1 · plate export block · shortlist promote fail-closed · scale ban."""

from __future__ import annotations

import builtins
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _film_with_two_takes() -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "receipts").mkdir()
    (root / "takes" / "s1").mkdir(parents=True)
    (root / "takes" / "s1" / "a.mp4").write_bytes(b"\x00" * 200)
    (root / "takes" / "s1" / "b.mp4").write_bytes(b"\x00" * 200)
    (root / "film-spec.json").write_text(
        json.dumps({"scenes": [{"shots": [{"id": "s1"}]}]}),
        encoding="utf-8",
    )
    (root / "manifest.json").write_text(json.dumps({"clips": {}}), encoding="utf-8")
    return root


class TestShortlistPromoteFailClosed(unittest.TestCase):
    def test_promote_blocked_when_anti_hijack_unavailable(self) -> None:
        from workflow_pack import select_shortlist

        root = _film_with_two_takes()
        real_import = builtins.__import__

        def _imp(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
            if name == "composition_anti_hijack":
                raise ImportError("simulated missing anti-hijack")
            return real_import(name, globals, locals, fromlist, level)

        env = {k: v for k, v in os.environ.items() if k != "AIFILM_SKIP_ANTI_HIJACK"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch("builtins.__import__", side_effect=_imp):
                out = select_shortlist(root, write=True, promote=True, measure_missing=False)

        # multi_take_count = number of shots with ≥2 takes (here 1 shot)
        self.assertGreaterEqual(int(out.get("multi_take_count") or 0), 1)
        self.assertGreaterEqual(int((out.get("shots") or [{}])[0].get("take_count") or 0), 2)
        self.assertFalse(out.get("anti_hijack_enabled"))
        self.assertTrue(out.get("promote_blocked"))
        self.assertFalse(out.get("ok"))
        self.assertIn("SHORTLIST_MEAN_ONLY_NO_ANTI_HIJACK", out.get("codes") or [])
        self.assertIn("SHORTLIST_PROMOTE_BLOCKED_MEAN_ONLY", out.get("codes") or [])
        self.assertEqual(out.get("promoted") or [], [])
        self.assertFalse(out.get("did_promote"))
        man = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(man.get("clips") or {}, {})

    def test_intentional_skip_allows_promote_but_logs_mean_only(self) -> None:
        from workflow_pack import select_shortlist

        root = _film_with_two_takes()
        with mock.patch.dict(os.environ, {"AIFILM_SKIP_ANTI_HIJACK": "1"}, clear=False):
            out = select_shortlist(root, write=True, promote=True, measure_missing=False)
        self.assertIn("SHORTLIST_MEAN_ONLY_NO_ANTI_HIJACK", out.get("codes") or [])
        self.assertFalse(out.get("promote_blocked"))
        self.assertTrue(out.get("ok"))


class TestExportDesktopPlateBlock(unittest.TestCase):
    def test_plate_blocks_helper_flags_conflict(self) -> None:
        from final.delivery_class import plate_blocks_final_complete

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rec = root / "receipts"
            rec.mkdir()
            (rec / "official-final-report.json").write_text(
                json.dumps({"status": "OFFICIAL_FINAL_PLATE", "master_lock": False}),
                encoding="utf-8",
            )
            adv = plate_blocks_final_complete(root, gates={"final_complete": True})
            self.assertTrue(adv.get("blocks_ship_complete"))
            self.assertIn("PLATE_CLAIMED_FINAL_COMPLETE", adv.get("codes") or [])

    def test_export_desktop_refuses_plate(self) -> None:
        """cmd_export_desktop raises FilmError when official plate + final_complete."""
        from util.errors import FilmError

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "out").mkdir()
            (root / "out" / "film_final.mp4").write_bytes(b"x")
            rec = root / "receipts"
            rec.mkdir()
            (rec / "official-final-report.json").write_text(
                json.dumps({"status": "OFFICIAL_FINAL_PLATE", "master_lock": False}),
                encoding="utf-8",
            )
            man = {
                "title": "t",
                "gates": {
                    "final_complete": True,
                    "clips_complete": True,
                    "desktop_exported": False,
                },
            }
            (root / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
            import argparse

            from cli.cli_post import cmd_export_desktop

            args = argparse.Namespace(root=str(root), name="N1TestPlate", force=True)
            with mock.patch("cli.cli_post.recompute_gates", lambda *a, **k: None):
                with mock.patch("cli.cli_post.load_manifest", return_value=man):
                    with self.assertRaises(FilmError) as ctx:
                        cmd_export_desktop(args)
            self.assertIn("plate", str(ctx.exception).lower())


class TestScalePromoteBanNested(unittest.TestCase):
    def test_nested_decision_promote_ban(self) -> None:
        from narrative.scale_fallback import decide_scale_fallback

        d = decide_scale_fallback(consecutive_poison=3, target_tier="bare")
        self.assertTrue(d["promote_ban"])
        self.assertIn("SCALE_HARD_ON_BAN", d["codes"])


class TestCloseoutPlate(unittest.TestCase):
    def test_closeout_blocks_final_complete(self) -> None:
        from closeout import closeout_status

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "out").mkdir()
            (root / "out" / "film_final.mp4").write_bytes(b"fake")
            rec = root / "receipts"
            rec.mkdir()
            (rec / "official-final-report.json").write_text(
                json.dumps({"status": "OFFICIAL_FINAL_PLATE"}),
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                json.dumps({"gates": {"final_complete": True}}),
                encoding="utf-8",
            )
            st = closeout_status(root)
            step = next(s for s in st["steps"] if s["id"] == "final_complete")
            self.assertFalse(step["ok"])


if __name__ == "__main__":
    unittest.main()
