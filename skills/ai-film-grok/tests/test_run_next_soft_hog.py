"""Honesty-rail R4.1 · run-next soft-hog + until-empty ownership contracts."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

pytestmark = pytest.mark.hotpath


class TestRunNextSoftHog(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("AIFILM_I_OWN_THE_GPU", None)

    def test_gpu_no_hog_until_empty_refuses_unowned(self) -> None:
        from h3_fill_idle import gpu_no_hog_decision

        dec = gpu_no_hog_decision(
            queue_busy=False, i_own_gpu=False, mode="until_empty", execute=True
        )
        self.assertEqual(dec["decision"], "refused")
        self.assertEqual(dec["reason_code"], "until_empty_requires_ownership")

    def test_busy_unowned_hold_zero_submit(self) -> None:
        from h3_fill_idle import gpu_no_hog_decision

        dec = gpu_no_hog_decision(
            queue_busy=True, i_own_gpu=False, mode="run_next", execute=True
        )
        self.assertEqual(dec["decision"], "hold")
        self.assertEqual(dec["reason_code"], "no_hog_busy_hold")

    def test_unowned_execute_soft_caps_max_jobs_five(self) -> None:
        from h3_fill_idle import run_next_fill_idle

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            os.environ.pop("AIFILM_I_OWN_THE_GPU", None)
            with mock.patch("h3_fill_idle._foreign_gpu_lease", return_value=None):
                with mock.patch(
                    "h3_fill_idle.probe_comfy_capacity_soft",
                    return_value={
                        "ok": True,
                        "ready": True,
                        "status": "ready",
                        "blockers": [],
                    },
                ):
                    with mock.patch(
                        "h3_fill_idle.next_fill_idle_job",
                        return_value={"ok": True, "next": None, "pending_count": 0},
                    ):
                        out = run_next_fill_idle(
                            root,
                            execute=True,
                            max_jobs=20,
                            register=False,
                            i_own_the_gpu=False,
                        )
        self.assertEqual(out.get("max_jobs"), 5)
        self.assertFalse(out.get("i_own_the_gpu"))

    def test_owned_allows_higher_max_jobs(self) -> None:
        from h3_fill_idle import run_next_fill_idle

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text("{}", encoding="utf-8")
            with mock.patch("h3_fill_idle._foreign_gpu_lease", return_value=None):
                with mock.patch(
                    "h3_fill_idle.probe_comfy_capacity_soft",
                    return_value={
                        "ok": True,
                        "ready": True,
                        "status": "ready",
                        "blockers": [],
                    },
                ):
                    with mock.patch(
                        "h3_fill_idle.next_fill_idle_job",
                        return_value={"ok": True, "next": None, "pending_count": 0},
                    ):
                        out = run_next_fill_idle(
                            root,
                            execute=True,
                            max_jobs=12,
                            register=False,
                            i_own_the_gpu=True,
                        )
        self.assertEqual(out.get("max_jobs"), 12)

    def test_until_empty_execute_writes_receipt_without_own(self) -> None:
        from h3_fill_idle import fill_idle_until_empty
        from util import write_json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "film-spec.json",
                {"title": "soft-hog", "scenes": [{"shots": [{"id": "s1"}]}]},
            )
            with mock.patch.dict("os.environ", {"AIFILM_I_OWN_THE_GPU": ""}, clear=False):
                with mock.patch("h3_fill_idle._foreign_gpu_lease", return_value=None):
                    rep = fill_idle_until_empty(
                        root, execute=True, i_own_the_gpu=False, max_cycles=1
                    )
            self.assertEqual(rep.get("stop_reason"), "exclusive_gpu_required")
            self.assertEqual(rep.get("open_ops_status"), "OPEN_OPS")
            self.assertEqual(rep.get("open_ops_reason"), "exclusive_gpu_required")
            self.assertTrue((root / "receipts" / "fill-idle-until-empty.json").is_file())


if __name__ == "__main__":
    unittest.main()
