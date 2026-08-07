from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from h3_fill_idle import (  # noqa: E402
    gpu_no_hog_decision,
    gpu_no_hog_report,
)

pytestmark = pytest.mark.hotpath


class NoHogDecisionTests(unittest.TestCase):
    def test_dry_run_always_proceeds(self):
        for busy in (False, True):
            dec = gpu_no_hog_decision(queue_busy=busy, execute=False)
            self.assertEqual(dec["decision"], "proceed")
            self.assertEqual(dec["reason_code"], "dry_run_allowed")

    def test_idle_not_owned_executes(self):
        dec = gpu_no_hog_decision(queue_busy=False, i_own_gpu=False, execute=True)
        self.assertEqual(dec["decision"], "proceed")
        self.assertEqual(dec["reason_code"], "no_hog_ok")

    def test_busy_not_owned_holds(self):
        dec = gpu_no_hog_decision(queue_busy=True, i_own_gpu=False, execute=True)
        self.assertEqual(dec["decision"], "hold")
        self.assertEqual(dec["reason_code"], "no_hog_busy_hold")

    def test_busy_owned_overrides(self):
        dec = gpu_no_hog_decision(queue_busy=True, i_own_gpu=True, execute=True)
        self.assertEqual(dec["decision"], "proceed")
        self.assertEqual(dec["reason_code"], "no_hog_ok")

    def test_until_empty_requires_ownership(self):
        dec = gpu_no_hog_decision(
            queue_busy=False, i_own_gpu=False, mode="until_empty", execute=True
        )
        self.assertEqual(dec["decision"], "refused")
        self.assertEqual(dec["reason_code"], "until_empty_requires_ownership")

    def test_until_empty_owned_proceeds(self):
        dec = gpu_no_hog_decision(
            queue_busy=False, i_own_gpu=True, mode="until_empty", execute=True
        )
        self.assertEqual(dec["decision"], "proceed")
        self.assertEqual(dec["reason_code"], "no_hog_ok")

    def test_until_empty_busy_not_owned_refused(self):
        dec = gpu_no_hog_decision(
            queue_busy=True, i_own_gpu=False, mode="until_empty", execute=True
        )
        # ownership gate wins over busy-hold; either way it must not submit.
        self.assertIn(dec["decision"], {"refused", "hold"})
        self.assertNotEqual(dec["decision"], "proceed")

    def test_report_wraps_decision(self):
        rep = gpu_no_hog_report(queue_busy=True, i_own_gpu=False, execute=True)
        self.assertEqual(rep["kind"], "ai-film-gpu-no-hog")
        self.assertTrue(rep["holds"])
        self.assertEqual(rep["reason_code"], "no_hog_busy_hold")
        self.assertTrue(rep["queue_busy"])
        self.assertFalse(rep["owned"])

    def test_report_no_hold_when_idle(self):
        rep = gpu_no_hog_report(queue_busy=False, i_own_gpu=False, execute=True)
        self.assertFalse(rep["holds"])
        self.assertEqual(rep["reason_code"], "no_hog_ok")


class NoHogEnvOverrideTests(unittest.TestCase):
    def test_env_own_overrides_busy(self):
        old = os.environ.get("AIFILM_I_OWN_THE_GPU")
        os.environ["AIFILM_I_OWN_THE_GPU"] = "1"
        try:
            # decision() takes an explicit flag; the live guard reads the env via
            # _env_i_own_the_gpu(). Verify the equivalence here.
            from h3_fill_idle import _env_i_own_the_gpu

            self.assertTrue(_env_i_own_the_gpu())
            dec = gpu_no_hog_decision(
                queue_busy=True, i_own_gpu=_env_i_own_the_gpu(), execute=True
            )
            self.assertEqual(dec["decision"], "proceed")
        finally:
            if old is None:
                os.environ.pop("AIFILM_I_OWN_THE_GPU", None)
            else:
                os.environ["AIFILM_I_OWN_THE_GPU"] = old


class TestNoHogWiredGuard:
    """The explicit guard must fire before any job submission when the queue is
    busy with foreign jobs — even if the capacity probe would otherwise report
    ready. It must NOT fire when idle. Deterministic via mocked probe + planner."""

    @staticmethod
    def _patch(monkeypatch, *, busy, owned_env=False, foreign_lease=None):
        import h3_fill_idle

        def fake_probe():
            blockers = [{"code": "COMFY_QUEUE_BUSY"}] if busy else []
            return {
                "ok": True,
                "ready": True,  # simulate the gap: ready=True yet busy blocker present
                "status": "ready",
                "blockers": blockers,
                "base_url": "http://127.0.0.1:18188",
                "source": "submission_capacity",
            }

        monkeypatch.setattr(h3_fill_idle, "probe_comfy_capacity_soft", fake_probe)
        # I5: isolate dual-film lease from host ~/.grok/run
        monkeypatch.setattr(
            h3_fill_idle,
            "_foreign_gpu_lease",
            lambda *_a, **_k: foreign_lease,
        )
        # Keep the planner benign: no next job -> caller returns queue_empty
        # without touching run_h3_shot / filesystem.
        monkeypatch.setattr(
            h3_fill_idle,
            "next_fill_idle_job",
            lambda *a, **k: {"next": None, "capacity_ready": not busy},
        )
        if owned_env:
            monkeypatch.setenv("AIFILM_I_OWN_THE_GPU", "1")
        else:
            monkeypatch.delenv("AIFILM_I_OWN_THE_GPU", raising=False)

    def test_guard_holds_when_busy(self, monkeypatch):
        self._patch(monkeypatch, busy=True)
        import h3_fill_idle

        out = h3_fill_idle.run_next_fill_idle(
            Path("/tmp"), execute=True, max_jobs=1, register=False
        )
        assert out.get("skipped_reason") == "no_hog_busy_hold"
        assert out.get("ok") is True
        assert out.get("partial") is True
        assert out.get("halt_reason_code") == "RUN_NO_HOG_BUSY_HOLD"
        assert out.get("no_hog") is not None
        assert out.get("open_ops")

    def test_guard_passes_when_idle(self, monkeypatch):
        self._patch(monkeypatch, busy=False)
        import h3_fill_idle

        out = h3_fill_idle.run_next_fill_idle(
            Path("/tmp"), execute=True, max_jobs=1, register=False
        )
        # Not busy -> guard does not fire; planner reports empty -> queue_empty.
        assert out.get("skipped_reason") != "no_hog_busy_hold"
        assert out.get("skipped_reason") == "queue_empty"

    def test_guard_owned_override_when_busy(self, monkeypatch):
        self._patch(monkeypatch, busy=True, owned_env=True)
        import h3_fill_idle

        out = h3_fill_idle.run_next_fill_idle(
            Path("/tmp"), execute=True, max_jobs=1, register=False
        )
        # Ownership bypasses the hold even when busy.
        assert out.get("skipped_reason") != "no_hog_busy_hold"
        assert out.get("skipped_reason") == "queue_empty"

    def test_foreign_lease_blocks_run_next(self, monkeypatch):
        foreign = {
            "ok": False,
            "free": False,
            "owned_by_self": False,
            "owner": "/other/film",
            "code": "LEASE_HELD",
        }
        self._patch(monkeypatch, busy=False, foreign_lease=foreign)
        import h3_fill_idle

        out = h3_fill_idle.run_next_fill_idle(
            Path("/tmp"), execute=True, max_jobs=3, register=False
        )
        assert out.get("skipped_reason") == "lease_held_foreign"
        assert out.get("partial") is True
        assert out.get("halt_reason_code") == "RUN_LEASE_HELD_FOREIGN"
        assert out.get("jobs_ran") == 0

    def test_unowned_max_jobs_soft_cap_five(self, monkeypatch):
        self._patch(monkeypatch, busy=False)
        import h3_fill_idle

        monkeypatch.delenv("AIFILM_I_OWN_THE_GPU", raising=False)
        out = h3_fill_idle.run_next_fill_idle(
            Path("/tmp"), execute=True, max_jobs=20, register=False
        )
        assert out.get("max_jobs") == 5
        assert out.get("skipped_reason") == "queue_empty"

    def test_owned_allows_higher_max_jobs(self, monkeypatch):
        self._patch(monkeypatch, busy=False, owned_env=True)
        import h3_fill_idle

        out = h3_fill_idle.run_next_fill_idle(
            Path("/tmp"),
            execute=True,
            max_jobs=12,
            register=False,
            i_own_the_gpu=True,
        )
        assert out.get("max_jobs") == 12


if __name__ == "__main__":
    unittest.main()
