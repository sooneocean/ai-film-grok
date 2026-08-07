"""Honesty-rail R1 · skip_audit contract scenarios."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestSkipAudit(unittest.TestCase):
    def tearDown(self) -> None:
        for k in list(os.environ):
            if k.startswith("AIFILM_SKIP"):
                os.environ.pop(k, None)

    def test_skip_flag_first_write_usage(self) -> None:
        from core.skip_audit import skip_flag, load_skip_usage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["AIFILM_SKIP_GATE_AUTO"] = "1"
            self.assertTrue(skip_flag("AIFILM_SKIP_GATE_AUTO", film_root=root))
            usage = root / "receipts" / "skip-usage.json"
            self.assertTrue(usage.is_file())
            data = json.loads(usage.read_text(encoding="utf-8"))
            names = {e.get("name") for e in (data.get("entries") or [])}
            self.assertIn("AIFILM_SKIP_GATE_AUTO", names)
            self.assertEqual(len(load_skip_usage(root).get("entries") or []), 1)

    def test_idempotent_same_env_read(self) -> None:
        from core.skip_audit import skip_flag, load_skip_usage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["AIFILM_SKIP_CINEMATIC_GATE"] = "1"
            skip_flag("AIFILM_SKIP_CINEMATIC_GATE", film_root=root)
            skip_flag("AIFILM_SKIP_CINEMATIC_GATE", film_root=root)
            self.assertEqual(len(load_skip_usage(root).get("entries") or []), 1)

    def test_iron_unreasoned_partial(self) -> None:
        from core.skip_audit import record_skip_usage, verify_skip_usage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record_skip_usage(root, "AIFILM_SKIP_HEAT_FINAL_GATE", origin="env")
            ver = verify_skip_usage(root, sync_env=False)
            self.assertFalse(ver.get("ok"))
            self.assertEqual(ver.get("classification"), "PARTIAL")
            self.assertIn("AIFILM_SKIP_HEAT_FINAL_GATE", ver.get("skips_used") or [])

    def test_iron_with_reason_documented(self) -> None:
        from core.skip_audit import record_skip_usage, verify_skip_usage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record_skip_usage(
                root,
                "AIFILM_SKIP_HEAT_FINAL_GATE",
                origin="env",
                reason="canary only",
            )
            ver = verify_skip_usage(root, sync_env=False)
            self.assertTrue(ver.get("ok"))
            self.assertEqual(ver.get("classification"), "SKIP_DOCUMENTED")

    def test_clean_no_skips(self) -> None:
        from core.skip_audit import verify_skip_usage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ver = verify_skip_usage(root, sync_env=False)
            self.assertTrue(ver.get("ok"))
            self.assertEqual(ver.get("skips_used"), [])
            self.assertEqual(ver.get("classification"), "CLEAN")

    def test_sync_env_catches_legacy_direct_read(self) -> None:
        from core.skip_audit import verify_skip_usage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["AIFILM_SKIP_I2V_MOTION_GATE"] = "1"
            # never called skip_flag — closeout sync should still ledger
            ver = verify_skip_usage(root, sync_env=True)
            self.assertIn("AIFILM_SKIP_I2V_MOTION_GATE", ver.get("skips_used") or [])
            self.assertFalse(ver.get("ok"))  # iron, no reason

    def test_attach_skips_to_official_report(self) -> None:
        from core.skip_audit import record_skip_usage, attach_skips_to_report

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record_skip_usage(root, "AIFILM_SKIP_PILOT_GATE", reason="test")
            rep = attach_skips_to_report(
                {"status": "TECHNICAL_FINAL", "partial": False, "honest_limits": []},
                root,
            )
            self.assertIn("AIFILM_SKIP_PILOT_GATE", rep.get("skips_used") or [])
            self.assertEqual(rep["skip_audit"]["classification"], "SKIP_DOCUMENTED")


    def test_i2v_and_gate_auto_ledger(self) -> None:
        from gate_auto import skip_enabled as ga_skip
        from i2v_motion_gate import i2v_motion_gate_skip_enabled
        from core.skip_audit import load_skip_usage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["AIFILM_SKIP_GATE_AUTO"] = "1"
            os.environ["AIFILM_SKIP_I2V_MOTION_GATE"] = "1"
            self.assertTrue(ga_skip(root))
            self.assertTrue(i2v_motion_gate_skip_enabled(root))
            names = {e.get("name") for e in (load_skip_usage(root).get("entries") or [])}
            self.assertIn("AIFILM_SKIP_GATE_AUTO", names)

    def test_round2_hotpath_skips_ledger(self) -> None:
        """R5 follow-up: anti-hijack / generation / scale / fill / five-track via skip_flag."""
        from composition_anti_hijack import _env_skip as ah_skip
        from generation_request import generation_request_skip_strict
        from narrative.scale_fallback import scale_promote_skip
        from composition_fill_gate import _env_skip as fill_skip
        from five_track import policy_skip_enabled
        from core.skip_audit import load_skip_usage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["AIFILM_SKIP_ANTI_HIJACK"] = "1"
            os.environ["AIFILM_SKIP_GENERATION_REQUEST"] = "1"
            os.environ["AIFILM_SKIP_SCALE_PROMOTE_GATE"] = "1"
            os.environ["AIFILM_SKIP_COMPOSITION_FILL"] = "1"
            os.environ["AIFILM_SKIP_FIVE_TRACK"] = "1"
            try:
                self.assertTrue(ah_skip(root))
                self.assertTrue(generation_request_skip_strict(root))
                self.assertTrue(scale_promote_skip(root))
                self.assertTrue(fill_skip(root))
                self.assertTrue(policy_skip_enabled(root))
                names = {e.get("name") for e in (load_skip_usage(root).get("entries") or [])}
                for n in (
                    "AIFILM_SKIP_ANTI_HIJACK",
                    "AIFILM_SKIP_GENERATION_REQUEST",
                    "AIFILM_SKIP_SCALE_PROMOTE_GATE",
                    "AIFILM_SKIP_COMPOSITION_FILL",
                    "AIFILM_SKIP_FIVE_TRACK",
                ):
                    self.assertIn(n, names)
            finally:
                for k in (
                    "AIFILM_SKIP_ANTI_HIJACK",
                    "AIFILM_SKIP_GENERATION_REQUEST",
                    "AIFILM_SKIP_SCALE_PROMOTE_GATE",
                    "AIFILM_SKIP_COMPOSITION_FILL",
                    "AIFILM_SKIP_FIVE_TRACK",
                ):
                    os.environ.pop(k, None)

    def test_pilot_and_heat_queue_ledger(self) -> None:
        from production_gates import assert_pilot_user_approved, assert_heat_allows_media
        from core.skip_audit import load_skip_usage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["AIFILM_SKIP_PILOT_GATE"] = "1"
            os.environ["AIFILM_SKIP_HEAT_QUEUE_GATE"] = "1"
            rep = assert_pilot_user_approved(root, env_skip=True)
            self.assertTrue(rep.get("skipped"))
            rep2 = assert_heat_allows_media(root, env_skip=True)
            self.assertTrue(rep2.get("skipped"))
            names = {e.get("name") for e in (load_skip_usage(root).get("entries") or [])}
            self.assertIn("AIFILM_SKIP_PILOT_GATE", names)
            self.assertIn("AIFILM_SKIP_HEAT_QUEUE_GATE", names)


    def test_anti_boring_skip_ledger(self) -> None:
        from production_gates import assert_anti_boring_variety
        from core.skip_audit import load_skip_usage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["AIFILM_SKIP_ANTI_BORING_GATE"] = "1"
            rep = assert_anti_boring_variety(root, env_skip=True)
            self.assertTrue(rep.get("skipped"))
            names = {e.get("name") for e in (load_skip_usage(root).get("entries") or [])}
            self.assertIn("AIFILM_SKIP_ANTI_BORING_GATE", names)

    def test_iron_flags_include_production_secondaries(self) -> None:
        from core.skip_audit import IRON_SKIP_FLAGS

        for name in (
            "AIFILM_SKIP_ANTI_BORING_GATE",
            "AIFILM_SKIP_FACE_IDENTITY_GATE",
            "AIFILM_SKIP_CONTINUITY_GATE",
        ):
            self.assertIn(name, IRON_SKIP_FLAGS)


if __name__ == "__main__":
    unittest.main()
