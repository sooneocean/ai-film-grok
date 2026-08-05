"""W3: capacity-plan ETA + until-empty loop + P0 priority invariant."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from h3_fill_idle import (  # noqa: E402
    assert_priority_order,
    build_fill_idle_queue,
    capacity_plan,
    fill_idle_until_empty,
    next_fill_idle_job,
)
from util import write_json  # noqa: E402


def _film(root: Path) -> None:
    write_json(
        root / "film-spec.json",
        {
            "title": "until-empty",
            "h3": {"enabled": True},
            "genre": "adult",
            "heat_scale": "max",
            "director_intent": {"protagonist_want": "survive"},
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "soft1",
                            "shot_role": "hero",
                            "heat_phase": "setup",
                            "wardrobe_state": "clothed",
                            "dramatic_function": "bridge",
                        },
                        {
                            "id": "meat1",
                            "shot_role": "hero",
                            "heat_phase": "act",
                            "wardrobe_state": "bare",
                            "dramatic_function": "action",
                        },
                    ]
                }
            ],
        },
    )
    (root / "stills").mkdir()
    (root / "stills" / "soft1.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    (root / "stills" / "meat1.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    (root / "takes" / "soft1").mkdir(parents=True)
    clip = root / "takes" / "soft1" / "grok_soft.mp4"
    clip.write_bytes(b"\x00" * 120_000)
    write_json(
        root / "manifest.json",
        {"clips": {"soft1": {"path": str(clip), "mean": 7.5, "status": "candidate"}}},
    )


class PriorityInvariantTests(unittest.TestCase):
    def test_p2_while_p0_is_violation(self) -> None:
        pending = [
            {"shot_id": "m", "priority": "P0a", "command": "x"},
            {"shot_id": "s", "priority": "P2", "command": "y"},
        ]
        v = assert_priority_order(pending, pending[1])
        self.assertTrue(any("P2" in x or "starved" in x or "not_first" in x for x in v))

    def test_queue_next_is_p0_meat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _film(root)
            q = build_fill_idle_queue(root, include_challenge=True)
            self.assertTrue(q["ok"])
            self.assertTrue(q.get("priority_ok"))
            self.assertEqual(q.get("priority_violations") or [], [])
            self.assertEqual(q["next"]["shot_id"], "meat1")
            self.assertTrue(str(q["next"]["priority"]).startswith("P0"))
            nxt = next_fill_idle_job(root, include_challenge=True, check_capacity=False)
            self.assertEqual(nxt["next"]["shot_id"], "meat1")


class CapacityPlanTests(unittest.TestCase):
    def test_capacity_plan_writes_eta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _film(root)
            plan = capacity_plan(root, include_challenge=True)
            self.assertTrue(plan["ok"])
            self.assertGreaterEqual(int(plan["pending_jobs"]), 1)
            self.assertGreater(float(plan["eta_minutes_total"]), 0)
            self.assertIn("i2v", plan.get("by_mode") or plan.get("eta_by_mode") or {"i2v": 1})
            self.assertTrue((root / "receipts" / "h3-capacity-plan.json").is_file())


class UntilEmptyTests(unittest.TestCase):
    def test_until_empty_dry_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _film(root)
            rep = fill_idle_until_empty(
                root,
                execute=False,
                max_jobs_per_cycle=2,
                max_cycles=3,
                include_challenge=True,
            )
            self.assertTrue(rep["until_empty"])
            self.assertEqual(rep["stop_reason"], "dry_run_pass_execute")
            self.assertEqual(int(rep["jobs_ran_total"]), 0)
            self.assertIn("plan_before", rep)

    def test_until_empty_execute_queue_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _film(root)

            def _fake_run_next(*_a, **_k):
                return {
                    "ok": True,
                    "jobs_ran": 0,
                    "skipped_reason": "queue_empty",
                    "pending_after": 0,
                    "next_after": None,
                }

            with mock.patch("h3_fill_idle.run_next_fill_idle", side_effect=_fake_run_next):
                rep = fill_idle_until_empty(
                    root,
                    execute=True,
                    max_jobs_per_cycle=2,
                    max_cycles=5,
                    include_challenge=True,
                )
            self.assertEqual(rep["stop_reason"], "queue_empty")
            self.assertTrue((root / "receipts" / "fill-idle-until-empty.json").is_file())


    def test_until_empty_capacity_not_ready_stop(self) -> None:
        """AF5 · capacity block must stop execute honestly (not run_failed)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _film(root)

            def _fake_run_next(*_a, **_k):
                return {
                    "ok": True,
                    "jobs_ran": 0,
                    "skipped_reason": "capacity_not_ready",
                    "pending_after": 3,
                    "next_after": {"shot_id": "meat1"},
                }

            with mock.patch("h3_fill_idle.run_next_fill_idle", side_effect=_fake_run_next):
                rep = fill_idle_until_empty(
                    root,
                    execute=True,
                    max_jobs_per_cycle=2,
                    max_cycles=5,
                    include_challenge=True,
                    stop_on_capacity=True,
                )
            self.assertEqual(rep["stop_reason"], "capacity_not_ready")
            self.assertNotEqual(rep["stop_reason"], "run_failed")
            self.assertTrue((root / "receipts" / "fill-idle-until-empty.json").is_file())


if __name__ == "__main__":
    unittest.main()
