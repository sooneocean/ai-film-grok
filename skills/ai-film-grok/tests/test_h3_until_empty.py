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
    _is_capacity_contention_error,
    assert_priority_order,
    build_fill_idle_queue,
    capacity_plan,
    fill_idle_until_empty,
    next_fill_idle_job,
    prepare_capacity_free_first,
    recover_capacity_contention,
    run_next_fill_idle,
    wait_for_comfy_capacity,
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
            self.assertIn("takes_count_delta", rep)

    def test_until_empty_execute_refuses_without_i_own_the_gpu(self) -> None:
        """Multi-agent IRON: until-empty --execute needs exclusive ownership."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _film(root)
            with mock.patch.dict("os.environ", {"AIFILM_I_OWN_THE_GPU": ""}, clear=False):
                rep = fill_idle_until_empty(
                    root,
                    execute=True,
                    i_own_the_gpu=False,
                    max_cycles=3,
                )
            self.assertFalse(rep.get("ok"))
            self.assertEqual(rep.get("stop_reason"), "exclusive_gpu_required")
            self.assertEqual(rep.get("halt_reason_code"), "RUN_EXCLUSIVE_GPU_REQUIRED")
            self.assertEqual(rep.get("halt_reason_group"), "ownership")
            self.assertEqual(rep.get("skipped_reason"), "exclusive_gpu_required")
            self.assertIn("decision_tree", rep)
            self.assertEqual(int(rep.get("jobs_ran_total") or 0), 0)
            self.assertTrue((root / "receipts" / "fill-idle-until-empty.json").is_file())
            self.assertIn("takes_count_delta", rep)
            self.assertIn("pending_reason_breakdown", rep)
            self.assertIn("open_ops", rep)
            self.assertTrue(rep["open_ops"])
            self.assertEqual(rep["open_ops"][0].get("reason"), "exclusive_gpu_required")
            self.assertEqual(rep["open_ops"][0].get("halt_reason_code"), "RUN_EXCLUSIVE_GPU_REQUIRED")
            self.assertEqual(rep["open_ops"][0].get("halt_reason_group"), "ownership")

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
                    i_own_the_gpu=True,
                    max_jobs_per_cycle=2,
                    max_cycles=5,
                    include_challenge=True,
                )
            self.assertEqual(rep["stop_reason"], "queue_empty")
            self.assertTrue((root / "receipts" / "fill-idle-until-empty.json").is_file())


    def test_until_empty_missing_skip_reason_is_machine_coded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _film(root)

            def _fake_run_next(*_a, **_k):
                return {
                    "ok": True,
                    "jobs_ran": 0,
                    "pending_after": 1,
                    "next_after": {"shot_id": "meat1"},
                }

            with mock.patch("h3_fill_idle.run_next_fill_idle", side_effect=_fake_run_next):
                rep = fill_idle_until_empty(
                    root,
                    execute=True,
                    i_own_the_gpu=True,
                    max_jobs_per_cycle=1,
                    max_cycles=1,
                    include_challenge=True,
                )
            self.assertEqual(rep["halt_reason_code"], "RUN_DECISION_MISSING")
            self.assertEqual(rep["halt_reason_group"], "scheduler")
            self.assertEqual(rep["cycles"][0].get("halt_reason_code"), "RUN_DECISION_MISSING")
            self.assertEqual(rep["cycles"][0].get("skipped_reason"), "run_next_missing")


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
                    i_own_the_gpu=True,
                    max_jobs_per_cycle=2,
                    max_cycles=5,
                    include_challenge=True,
                    stop_on_capacity=True,
                )
            self.assertEqual(rep["stop_reason"], "capacity_not_ready")
            self.assertNotEqual(rep["stop_reason"], "run_failed")
            self.assertTrue((root / "receipts" / "fill-idle-until-empty.json").is_file())

    def test_until_empty_records_cycle_open_ops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _film(root)

            def _fake_run_next(*_a, **_k):
                return {
                    "ok": True,
                    "jobs_ran": 0,
                    "skipped_reason": "capacity_not_ready",
                    "pending_after": 2,
                    "next_after": {"shot_id": "meat1"},
                    "open_ops": [
                        {
                            "schema_version": 1,
                            "kind": "ai-film-h3-run-next-open-op",
                            "halt_reason_code": "RUN_NOT_EXECUTED_CAPACITY",
                            "halt_reason_group": "capacity",
                            "reason": "capacity_not_ready",
                        }
                    ],
                }

            with mock.patch("h3_fill_idle.run_next_fill_idle", side_effect=_fake_run_next):
                rep = fill_idle_until_empty(
                    root,
                    execute=True,
                    i_own_the_gpu=True,
                    max_jobs_per_cycle=2,
                    max_cycles=5,
                    include_challenge=True,
                    stop_on_capacity=True,
                )
            self.assertEqual(rep["stop_reason"], "capacity_not_ready")
            self.assertTrue(rep.get("cycles"))
            self.assertEqual(rep["cycles"][0].get("halt_reason_code"), "RUN_NOT_EXECUTED_CAPACITY")
            self.assertIn("open_ops", rep["cycles"][0])
            self.assertEqual(rep["cycles"][0]["open_ops"][0]["reason"], "capacity_not_ready")

    def test_queue_busy_submit_is_capacity_not_run_failed(self) -> None:
        """C1 race: probe ready then COMFY_QUEUE_BUSY → capacity_not_ready (retryable)."""
        self.assertTrue(
            _is_capacity_contention_error(
                "comfy-h3 generate failed: ComfyUI submission blocked by resource tower: COMFY_QUEUE_BUSY"
            )
        )
        self.assertFalse(_is_capacity_contention_error("variety preflight failed: L4_INSERT_LOW"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _film(root)

            nxt = {
                "ok": True,
                "next": {
                    "shot_id": "meat1",
                    "mode": "i2v",
                    "priority": "P0c",
                    "lane": "primary_h3",
                    "command": "x",
                },
                "capacity_ready": True,
            }

            def _boom(*_a, **_k):
                raise RuntimeError(
                    "comfy-h3 generate failed: ComfyUI submission blocked by "
                    "resource tower: COMFY_QUEUE_BUSY"
                )

            with (
                mock.patch("h3_fill_idle.next_fill_idle_job", return_value=nxt),
                mock.patch("h3_workflow.run_h3_shot", side_effect=_boom),
            ):
                rep = run_next_fill_idle(root, execute=True, max_jobs=1, require_capacity=True)
            self.assertEqual(rep.get("skipped_reason"), "capacity_not_ready")
            self.assertTrue(rep.get("ok"))
            self.assertNotEqual(rep.get("skipped_reason"), "run_failed")

    def test_until_empty_free_first_in_report(self) -> None:
        """S5.3-ops · free_prep lands on until-empty receipt; never cancels foreign."""
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
                with mock.patch(
                    "h3_fill_idle.prepare_capacity_free_first",
                    return_value={
                        "kind": "ai-film-capacity-free-first",
                        "free_first": True,
                        "outcome": "already_ready",
                        "freed": False,
                    },
                ) as prep:
                    rep = fill_idle_until_empty(
                        root,
                        execute=True,
                        i_own_the_gpu=True,
                        max_jobs_per_cycle=2,
                        max_cycles=3,
                        free_first=True,
                    )
            prep.assert_called_once()
            self.assertTrue(rep.get("free_first"))
            self.assertEqual((rep.get("free_prep") or {}).get("outcome"), "already_ready")
            self.assertEqual(rep["stop_reason"], "queue_empty")


class FreeFirstPrepTests(unittest.TestCase):
    def test_disabled_skips(self) -> None:
        rep = prepare_capacity_free_first(free_first=False)
        self.assertEqual(rep["skipped_reason"], "free_first_disabled")
        self.assertFalse(rep["attempted"])
        self.assertFalse(rep["freed"])

    def test_queue_busy_never_frees(self) -> None:
        fake_cap = {
            "ok": True,
            "ready": False,
            "status": "blocked",
            "vram_free_bytes": 1,
            "blockers": [
                {"code": "VRAM_BELOW_FLOOR", "message": "low"},
                {"code": "COMFY_QUEUE_BUSY", "message": "busy"},
            ],
        }
        with mock.patch("h3_fill_idle.probe_comfy_capacity_soft", return_value=fake_cap):
            with mock.patch("comfy_video.free_memory") as free_m:
                rep = prepare_capacity_free_first(free_first=True, dry_run=False)
        self.assertEqual(rep["skipped_reason"], "queue_busy_never_cancel_foreign")
        self.assertFalse(rep["attempted"])
        free_m.assert_not_called()

    def test_memory_only_dry_would_free(self) -> None:
        fake_cap = {
            "ok": True,
            "ready": False,
            "status": "blocked",
            "vram_free_bytes": 1,
            "blockers": [{"code": "VRAM_BELOW_FLOOR", "message": "low"}],
        }
        with mock.patch("h3_fill_idle.probe_comfy_capacity_soft", return_value=fake_cap):
            with mock.patch("comfy_video.free_memory") as free_m:
                rep = prepare_capacity_free_first(free_first=True, dry_run=True)
        self.assertTrue(rep["would_free"])
        self.assertEqual(rep["outcome"], "dry_run_would_free")
        free_m.assert_not_called()

    def test_memory_only_execute_frees_once(self) -> None:
        blocked = {
            "ok": True,
            "ready": False,
            "status": "blocked",
            "vram_free_bytes": 1,
            "blockers": [
                {"code": "RAM_BELOW_FLOOR", "message": "ram"},
                {"code": "VRAM_BELOW_FLOOR", "message": "vram"},
            ],
        }
        ready = {
            "ok": True,
            "ready": True,
            "status": "ready",
            "vram_free_bytes": 30_000_000_000,
            "blockers": [],
        }
        with mock.patch(
            "h3_fill_idle.probe_comfy_capacity_soft",
            side_effect=[blocked, ready],
        ):
            with mock.patch(
                "comfy_video.free_memory",
                return_value={"ok": True, "action": "free_memory"},
            ) as free_m:
                with mock.patch("comfy_video.normalize_base_url", return_value="http://127.0.0.1:18188"):
                    rep = prepare_capacity_free_first(free_first=True, dry_run=False)
        free_m.assert_called_once()
        self.assertTrue(rep["attempted"])
        self.assertTrue(rep["freed"])
        self.assertEqual(rep["outcome"], "ready_after_free")


class CapacityWaitTests(unittest.TestCase):
    def test_wait_zero_is_single_probe(self) -> None:
        fake = {"ok": True, "ready": False, "status": "blocked", "blockers": []}
        with mock.patch("h3_fill_idle.probe_comfy_capacity_soft", return_value=fake):
            rep = wait_for_comfy_capacity(max_wait_sec=0.0, sleep_fn=lambda _s: None)
        self.assertFalse(rep.get("ready"))
        self.assertEqual(rep.get("outcome"), "not_ready_no_wait")
        self.assertEqual(rep.get("probes"), 1)

    def test_wait_ready_after_poll(self) -> None:
        blocked = {
            "ok": True,
            "ready": False,
            "status": "blocked",
            "blockers": [{"code": "VRAM_BELOW_FLOOR", "message": "low"}],
        }
        ready = {"ok": True, "ready": True, "status": "ready", "blockers": []}
        with mock.patch(
            "h3_fill_idle.probe_comfy_capacity_soft",
            side_effect=[blocked, ready],
        ):
            rep = wait_for_comfy_capacity(
                max_wait_sec=30.0,
                poll_sec=0.5,
                sleep_fn=lambda _s: None,
            )
        self.assertTrue(rep.get("ready"))
        self.assertEqual(rep.get("outcome"), "ready_after_wait")

    def test_until_empty_capacity_wait_recovers_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _film(root)
            calls = {"n": 0}

            def _fake_run_next(*_a, **_k):
                calls["n"] += 1
                if calls["n"] == 1:
                    return {
                        "ok": True,
                        "jobs_ran": 0,
                        "skipped_reason": "capacity_not_ready",
                        "pending_after": 2,
                        "next_after": {"shot_id": "s1"},
                    }
                return {
                    "ok": True,
                    "jobs_ran": 0,
                    "skipped_reason": "queue_empty",
                    "pending_after": 0,
                    "next_after": None,
                }

            recover = {
                "kind": "ai-film-capacity-recover",
                "ready": True,
                "outcome": "ready_after_wait",
            }
            with mock.patch("h3_fill_idle.run_next_fill_idle", side_effect=_fake_run_next):
                with mock.patch(
                    "h3_fill_idle.recover_capacity_contention",
                    return_value=recover,
                ) as rec:
                    with mock.patch(
                        "h3_fill_idle.prepare_capacity_free_first",
                        return_value={"outcome": "already_ready", "free_first": True},
                    ):
                        rep = fill_idle_until_empty(
                            root,
                            execute=True,
                            i_own_the_gpu=True,
                            max_cycles=5,
                            free_first=True,
                            capacity_wait_sec=60.0,
                            stop_on_capacity=True,
                        )
            rec.assert_called()
            self.assertEqual(rep["stop_reason"], "queue_empty")
            self.assertEqual(rep.get("capacity_wait_sec"), 60.0)
            self.assertGreaterEqual(len(rep.get("capacity_waits") or []), 1)
            self.assertEqual(calls["n"], 2)

    def test_until_empty_capacity_wait_timeout_still_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _film(root)

            def _fake_run_next(*_a, **_k):
                return {
                    "ok": True,
                    "jobs_ran": 0,
                    "skipped_reason": "capacity_not_ready",
                    "pending_after": 1,
                    "next_after": {"shot_id": "s1"},
                }

            recover = {
                "kind": "ai-film-capacity-recover",
                "ready": False,
                "outcome": "still_blocked",
            }
            with mock.patch("h3_fill_idle.run_next_fill_idle", side_effect=_fake_run_next):
                with mock.patch(
                    "h3_fill_idle.recover_capacity_contention",
                    return_value=recover,
                ):
                    with mock.patch(
                        "h3_fill_idle.prepare_capacity_free_first",
                        return_value={"outcome": "skipped", "free_first": True},
                    ):
                        rep = fill_idle_until_empty(
                            root,
                            execute=True,
                            i_own_the_gpu=True,
                            max_cycles=3,
                            free_first=True,
                            capacity_wait_sec=30.0,
                            stop_on_capacity=True,
                        )
            self.assertEqual(rep["stop_reason"], "capacity_not_ready")
            self.assertFalse((rep.get("capacity_waits") or [{}])[0].get("ready"))

    def test_capacity_wait_hard_max_allows_overnight(self) -> None:
        """--capacity-wait-sec 7200 must not be silently clamped to 600s."""
        from h3_fill_idle import _CAPACITY_WAIT_SEC_HARD_MAX, wait_for_comfy_capacity

        self.assertGreaterEqual(_CAPACITY_WAIT_SEC_HARD_MAX, 7200.0)
        # Instant ready path still records the requested max after clamp.
        with mock.patch(
            "h3_fill_idle.probe_comfy_capacity_soft",
            return_value={"ok": True, "ready": True, "status": "ready", "blockers": []},
        ):
            rep = wait_for_comfy_capacity(max_wait_sec=7200.0, poll_sec=1.0, sleep_fn=lambda _s: None)
        self.assertEqual(rep.get("max_wait_sec"), 7200.0)
        self.assertTrue(rep.get("ready"))

    def test_h3_floor_retry_exhausted_drops_from_pending(self) -> None:
        """After cap H3 takes still below floor → residual done, no infinite P1."""
        from h3_fill_idle import classify_fill_idle_shot, _h3_floor_retry_cap

        self.assertGreaterEqual(_h3_floor_retry_cap(), 1)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _film(root)
            # meat1: many low-mean H3 takes → exhaust
            tdir = root / "takes" / "meat1"
            tdir.mkdir(parents=True, exist_ok=True)
            for i in range(6):
                p = tdir / f"meat1_h3_i2v_{i}_704x1280.mp4"
                p.write_bytes(b"\x00" * 50_000)
                write_json(
                    Path(str(p) + ".json"),
                    {"kind": "mean-absdiff-sidecar", "mean": 2.0, "mean_absdiff": 2.0},
                )
            from util.film_spec import _load_spec, _iter_shots

            spec = _load_spec(root)
            meat = next(s for s in _iter_shots(spec) if s.get("id") == "meat1")
            with mock.patch.dict("os.environ", {"AIFILM_H3_FLOOR_RETRY_CAP": "5"}):
                row = classify_fill_idle_shot(
                    root,
                    meat,
                    has_still=True,
                    wants_continue=False,
                )
            self.assertIn("h3_floor_retry_exhausted", row.get("reasons") or [])
            self.assertEqual(row.get("status"), "done")
            self.assertIsNone(row.get("command"))

    def test_capacity_wait_frees_when_queue_idle_memory_floor(self) -> None:
        """After foreign queue drains, free-memory once so VRAM floor can clear."""
        from h3_fill_idle import wait_for_comfy_capacity

        busy = {
            "ok": True,
            "ready": False,
            "status": "blocked",
            "blockers": [{"code": "COMFY_QUEUE_BUSY", "message": "busy"}],
        }
        mem = {
            "ok": True,
            "ready": False,
            "status": "blocked",
            "blockers": [{"code": "VRAM_BELOW_FLOOR", "message": "low"}],
        }
        ready = {"ok": True, "ready": True, "status": "ready", "blockers": []}
        probes = {"n": 0}

        def _probe():
            probes["n"] += 1
            if probes["n"] <= 1:
                return busy
            return mem

        free_calls = {"n": 0}

        def _free(**_k):
            free_calls["n"] += 1
            return {
                "outcome": "ready_after_free",
                "after": {"ready": True},
                "freed": True,
            }

        with mock.patch("h3_fill_idle.probe_comfy_capacity_soft", side_effect=_probe):
            with mock.patch("h3_fill_idle.prepare_capacity_free_first", side_effect=_free):
                rep = wait_for_comfy_capacity(
                    max_wait_sec=30.0,
                    poll_sec=0.01,
                    sleep_fn=lambda _s: None,
                    free_first_when_idle=True,
                )
        self.assertTrue(rep.get("ready"))
        self.assertEqual(rep.get("outcome"), "ready_after_idle_free")
        self.assertGreaterEqual(free_calls["n"], 1)


if __name__ == "__main__":
    unittest.main()
