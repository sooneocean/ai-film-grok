#!/usr/bin/env python3
"""Delivery Truth 2.36.4: export gate + film_core hard + zero_narration pure gate."""

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

from i2v_motion_gate import (  # noqa: E402
    I2VMotionGateError,
    assert_i2v_final_gate_for_export,
)


class ExportMotionGateTests(unittest.TestCase):
    def test_missing_gate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("AIFILM_SKIP_I2V_MOTION_GATE", None)
                with self.assertRaises(I2VMotionGateError):
                    assert_i2v_final_gate_for_export(root)

    def test_gate_false_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rec = root / "receipts"
            rec.mkdir()
            (rec / "i2v-final-gate.json").write_text(
                json.dumps({"ok": False, "kind": "i2v-final-gate"}),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("AIFILM_SKIP_I2V_MOTION_GATE", None)
                with self.assertRaises(I2VMotionGateError):
                    assert_i2v_final_gate_for_export(root)

    def test_gate_ok_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rec = root / "receipts"
            rec.mkdir()
            (rec / "i2v-final-gate.json").write_text(
                json.dumps({"ok": True, "kind": "i2v-final-gate"}),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("AIFILM_SKIP_I2V_MOTION_GATE", None)
                out = assert_i2v_final_gate_for_export(root)
            self.assertTrue(out["ok"])

    def test_escape_skips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with mock.patch.dict(os.environ, {"AIFILM_SKIP_I2V_MOTION_GATE": "1"}):
                out = assert_i2v_final_gate_for_export(root)
            self.assertTrue(out["ok"])
            self.assertTrue(out.get("skipped"))


class CloseoutFilmCoreTests(unittest.TestCase):
    def test_max_film_core_blocks_delivery(self) -> None:
        from closeout import closeout_status

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            (root / "out").mkdir()
            (root / "film-spec.json").write_text(
                json.dumps(
                    {
                        "title": "max-film",
                        "heat_scale": "max",
                        "vo_mode": "dialogue_drama",
                        "scenes": [],
                    }
                ),
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "gates": {
                            "final_complete": True,
                            "clips_complete": True,
                            "desktop_exported": False,
                        },
                        "outputs": {"final": "out/film_final.mp4"},
                    }
                ),
                encoding="utf-8",
            )
            (root / "out" / "film_final.mp4").write_bytes(b"\x00\x00fake")
            (root / "receipts" / "i2v-final-gate.json").write_text(
                json.dumps({"ok": True}), encoding="utf-8"
            )
            with mock.patch(
                "workflow_pack.film_core_closeout_audit",
                return_value={
                    "ok": False,
                    "issues": [{"code": "CORE_WANT_MISSING"}],
                    "next_cmd": "fix",
                },
            ):
                with mock.patch(
                    "heat_check.heat_agent_status",
                    return_value={"active": False, "ok": True, "hard_fail": False},
                ):
                    with mock.patch(
                        "closeout._post_audit_current",
                        return_value={"ok": True, "current": True},
                    ):
                        st = closeout_status(root)
            film = next(s for s in st["steps"] if s["id"] == "film_core")
            self.assertFalse(film["ok"])
            self.assertTrue(film.get("hard"))
            self.assertFalse(st.get("delivery_ready"))
            self.assertEqual(st.get("blocked_by"), "film_core")

    def test_film_core_exception_not_ok(self) -> None:
        from closeout import closeout_status

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            (root / "film-spec.json").write_text(
                json.dumps({"title": "x", "heat_scale": "soft", "scenes": []}),
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                json.dumps({"gates": {}, "outputs": {}}),
                encoding="utf-8",
            )
            (root / "receipts" / "i2v-final-gate.json").write_text(
                json.dumps({"ok": True}), encoding="utf-8"
            )
            with mock.patch(
                "workflow_pack.film_core_closeout_audit",
                side_effect=RuntimeError("boom"),
            ):
                with mock.patch(
                    "heat_check.heat_agent_status",
                    return_value={"active": False, "ok": True, "hard_fail": False},
                ):
                    with mock.patch(
                        "closeout._post_audit_current",
                        return_value={"ok": True, "current": True},
                    ):
                        st = closeout_status(root)
            film = next(s for s in st["steps"] if s["id"] == "film_core")
            self.assertFalse(film["ok"])
            self.assertIn("error", film.get("detail", "").lower())


if __name__ == "__main__":
    unittest.main()
