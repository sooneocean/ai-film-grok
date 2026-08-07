"""Optimization round · A1 gate silent-fix + scale promote + iron-status."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestGateAutoPromoteRespectsShortlist(unittest.TestCase):
    def test_promote_single_not_ok_when_shortlist_blocked(self) -> None:
        from gate_auto import auto_promote_single_takes

        root = Path(tempfile.mkdtemp())
        (root / "receipts").mkdir()
        (root / "takes" / "s1").mkdir(parents=True)
        (root / "takes" / "s1" / "a.mp4").write_bytes(b"\x00" * 200)
        (root / "takes" / "s1" / "b.mp4").write_bytes(b"\x00" * 200)
        (root / "film-spec.json").write_text(
            json.dumps({"scenes": [{"shots": [{"id": "s1"}]}]}), encoding="utf-8"
        )
        (root / "manifest.json").write_text(json.dumps({"clips": {}}), encoding="utf-8")

        # Force shortlist to report blocked
        fake = {
            "ok": False,
            "promote_blocked": True,
            "promoted": [],
            "codes": ["SHORTLIST_PROMOTE_BLOCKED_MEAN_ONLY"],
            "shots": [{"shot_id": "s1", "take_count": 2}],
        }
        with mock.patch("workflow_pack.select_shortlist", return_value=fake):
            rep = auto_promote_single_takes(root)
        self.assertFalse(rep.get("ok"))
        self.assertTrue(rep.get("promote_blocked"))


class TestScalePromoteShared(unittest.TestCase):
    def test_ban_blocks_without_note(self) -> None:
        from narrative.scale_fallback import ScalePromoteBanError, assert_scale_promote_allowed

        root = Path(tempfile.mkdtemp())
        (root / "receipts").mkdir()
        (root / "receipts" / "scale-fallback.json").write_text(
            json.dumps({"promote_ban": True, "codes": ["SCALE_HARD_ON_BAN"]}),
            encoding="utf-8",
        )
        env = {k: v for k, v in os.environ.items() if k != "AIFILM_SKIP_SCALE_PROMOTE_GATE"}
        with mock.patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ScalePromoteBanError):
                assert_scale_promote_allowed(root, review_note="looks fine", kind="still")

    def test_note_allows(self) -> None:
        from narrative.scale_fallback import assert_scale_promote_allowed

        root = Path(tempfile.mkdtemp())
        (root / "receipts").mkdir()
        (root / "receipts" / "scale-fallback.json").write_text(
            json.dumps({"decision": {"promote_ban": True, "codes": ["SCALE_HARD_ON_BAN"]}}),
            encoding="utf-8",
        )
        env = {k: v for k, v in os.environ.items() if k != "AIFILM_SKIP_SCALE_PROMOTE_GATE"}
        with mock.patch.dict(os.environ, env, clear=True):
            rep = assert_scale_promote_allowed(
                root, review_note="soft-max accepted after review", kind="clip"
            )
        self.assertTrue(rep.get("human_accepted"))


class TestIronStatus(unittest.TestCase):
    def test_report_lists_gates(self) -> None:
        from gates.iron_status import iron_status_report

        rep = iron_status_report()
        self.assertEqual(rep.get("kind"), "iron-status")
        self.assertGreaterEqual(len(rep.get("gates") or []), 10)
        self.assertIn("floors", rep)

    def test_cmd_exit(self) -> None:
        import argparse

        from cli.cli_status import cmd_iron_status

        args = argparse.Namespace(root=None, strict=False)
        with mock.patch("core.emit.emit"):
            code = cmd_iron_status(args)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
