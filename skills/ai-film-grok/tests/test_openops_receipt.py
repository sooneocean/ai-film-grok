"""Honesty-rail R4.3 · drain end = queue_empty or OPEN_OPS+reason (machine receipt)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestOpenOpsReceipt(unittest.TestCase):
    def test_attach_queue_empty(self) -> None:
        from h3_fill_idle import attach_open_ops_status

        rep = attach_open_ops_status({"stop_reason": "queue_empty", "open_ops": []})
        self.assertEqual(rep["open_ops_status"], "queue_empty")
        self.assertIsNone(rep["open_ops_reason"])

    def test_attach_open_ops_reasons(self) -> None:
        from h3_fill_idle import attach_open_ops_status

        for reason in (
            "exclusive_gpu_required",
            "lease_held_foreign",
            "capacity_not_ready",
            "max_cycles",
        ):
            rep = attach_open_ops_status({"stop_reason": reason})
            self.assertEqual(rep["open_ops_status"], "OPEN_OPS")
            self.assertEqual(rep["open_ops_reason"], reason)

    def test_until_empty_queue_empty_receipt(self) -> None:
        from h3_fill_idle import fill_idle_until_empty
        from util import write_json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "film-spec.json",
                {
                    "title": "openops",
                    "h3": {"enabled": True},
                    "scenes": [{"shots": [{"id": "s1", "shot_role": "hero"}]}],
                },
            )

            def _fake_run(*_a, **_k):
                return {
                    "ok": True,
                    "jobs_ran": 0,
                    "skipped_reason": "queue_empty",
                    "pending_after": 0,
                    "open_ops": [
                        {
                            "reason": "queue_empty",
                            "halt_reason_code": "RUN_QUEUE_EMPTY",
                        }
                    ],
                }

            with mock.patch("h3_fill_idle._foreign_gpu_lease", return_value=None):
                with mock.patch("h3_fill_idle.run_next_fill_idle", side_effect=_fake_run):
                    rep = fill_idle_until_empty(
                        root,
                        execute=True,
                        i_own_the_gpu=True,
                        max_cycles=2,
                    )
            self.assertEqual(rep.get("stop_reason"), "queue_empty")
            self.assertEqual(rep.get("open_ops_status"), "queue_empty")
            path = root / "receipts" / "fill-idle-until-empty.json"
            self.assertTrue(path.is_file())
            disk = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(disk.get("open_ops_status"), "queue_empty")

    def test_until_empty_exclusive_is_open_ops_not_crash(self) -> None:
        from h3_fill_idle import fill_idle_until_empty
        from util import write_json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / "film-spec.json", {"title": "x", "scenes": []})
            with mock.patch.dict("os.environ", {"AIFILM_I_OWN_THE_GPU": ""}, clear=False):
                with mock.patch("h3_fill_idle._foreign_gpu_lease", return_value=None):
                    rep = fill_idle_until_empty(
                        root, execute=True, i_own_the_gpu=False, max_cycles=1
                    )
            self.assertEqual(rep.get("open_ops_status"), "OPEN_OPS")
            self.assertEqual(rep.get("open_ops_reason"), "exclusive_gpu_required")
            self.assertFalse(rep.get("ok"))
            # engineering fail would omit open_ops_status — must be present
            disk = json.loads(
                (root / "receipts" / "fill-idle-until-empty.json").read_text(encoding="utf-8")
            )
            self.assertEqual(disk.get("open_ops_status"), "OPEN_OPS")


if __name__ == "__main__":
    unittest.main()
