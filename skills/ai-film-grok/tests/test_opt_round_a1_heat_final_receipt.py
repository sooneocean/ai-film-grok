"""A1 · heat-final receipt write must not silent-pass; skip_audit ledger."""

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


class TestHeatFinalReceiptWrite(unittest.TestCase):
    def test_write_failure_fail_closed(self) -> None:
        from production_gates import ProductionGateError, assert_heat_allows_final

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            # heat inactive path returns ok without write when not active —
            # force active final_ok via heat_agent_status mock
            with mock.patch(
                "heat_check.heat_agent_status",
                return_value={
                    "active": True,
                    "final_ok": True,
                    "hard_fail": False,
                    "score": 95,
                    "grade": "S",
                    "target_s": 90,
                    "floor": 70,
                },
            ):
                with mock.patch(
                    "util.write_json",
                    side_effect=OSError("disk full"),
                ):
                    with self.assertRaises(ProductionGateError) as ctx:
                        assert_heat_allows_final(root, env_skip=False, write_receipt=True)
            self.assertIn("heat-final-gate", str(ctx.exception))

    def test_env_skip_ledgers_usage(self) -> None:
        from production_gates import assert_heat_allows_final

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            os.environ["AIFILM_SKIP_HEAT_FINAL_GATE"] = "1"
            os.environ.pop("AIFILM_SKIP_REASON", None)
            try:
                rep = assert_heat_allows_final(root, env_skip=True)
                self.assertTrue(rep.get("skipped"))
                usage = root / "receipts" / "skip-usage.json"
                self.assertTrue(usage.is_file(), msg="skip-usage ledger missing")
                data = json.loads(usage.read_text(encoding="utf-8"))
                names = {e.get("name") for e in (data.get("entries") or [])}
                self.assertIn("AIFILM_SKIP_HEAT_FINAL_GATE", names)
            finally:
                os.environ.pop("AIFILM_SKIP_HEAT_FINAL_GATE", None)


class TestSkipAuditCore(unittest.TestCase):
    def test_skip_flag_idempotent(self) -> None:
        from core.skip_audit import skip_flag, load_skip_usage, verify_skip_usage

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.environ["AIFILM_SKIP_CINEMATIC_GATE"] = "1"
            try:
                self.assertTrue(skip_flag("AIFILM_SKIP_CINEMATIC_GATE", film_root=root))
                self.assertTrue(skip_flag("AIFILM_SKIP_CINEMATIC_GATE", film_root=root))
                ledger = load_skip_usage(root)
                self.assertEqual(len(ledger.get("entries") or []), 1)
                ver = verify_skip_usage(root)
                self.assertFalse(ver.get("ok"))
                self.assertEqual(ver.get("classification"), "PARTIAL")
                # with reason → documented
                os.environ["AIFILM_SKIP_REASON"] = "pilot demo only"
                # re-record reason on existing entry
                from core.skip_audit import record_skip_usage

                record_skip_usage(
                    root,
                    "AIFILM_SKIP_CINEMATIC_GATE",
                    reason="pilot demo only",
                )
                ver2 = verify_skip_usage(root)
                self.assertTrue(ver2.get("ok"))
                self.assertEqual(ver2.get("classification"), "SKIP_DOCUMENTED")
            finally:
                os.environ.pop("AIFILM_SKIP_CINEMATIC_GATE", None)
                os.environ.pop("AIFILM_SKIP_REASON", None)


if __name__ == "__main__":
    unittest.main()
