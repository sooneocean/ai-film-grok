"""Antifragility AF1–AF6 residual gaps (2026-08-05)."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from closeout import closeout_status  # noqa: E402
from h3_fill_idle import fill_idle_until_empty  # noqa: E402
from media_queue import note_queue_partial  # noqa: E402
from util import read_json, write_json  # noqa: E402
from util.subprocess import run as util_run  # noqa: E402


class AF1SubprocessTimeoutTests(unittest.TestCase):
    def test_util_run_timeout_raises(self) -> None:
        with self.assertRaises(subprocess.TimeoutExpired):
            util_run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2)

    def test_h3_soft_identity_midframe_has_timeout(self) -> None:
        src = (SCRIPTS / "h3_fill_idle.py").read_text(encoding="utf-8")
        self.assertIn("timeout=30", src)
        self.assertIn("identity_midframe_timeout_or_fail", src)
        # midframe path must not use bare subprocess without timeout
        block = src.split("def _soft_identity_penalty")[1].split("def score_take_for_pk")[0]
        self.assertIn("util_run", block)
        self.assertIn("timeout=30", block)


class AF5UntilEmptyCapacityTests(unittest.TestCase):
    def test_until_empty_capacity_not_ready_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(
                root / "film-spec.json",
                {
                    "title": "cap",
                    "h3": {"enabled": True},
                    "scenes": [{"shots": [{"id": "s1", "shot_role": "hero"}]}],
                },
            )

            def _fake_run_next(*_a, **_k):
                return {
                    "ok": True,
                    "jobs_ran": 0,
                    "skipped_reason": "capacity_not_ready",
                    "pending_after": 2,
                    "next_after": {"shot_id": "s1"},
                }

            with mock.patch("h3_fill_idle.run_next_fill_idle", side_effect=_fake_run_next):
                rep = fill_idle_until_empty(
                    root,
                    execute=True,
                    max_jobs_per_cycle=2,
                    max_cycles=5,
                    include_challenge=False,
                    stop_on_capacity=True,
                )
            self.assertEqual(rep["stop_reason"], "capacity_not_ready")
            self.assertTrue((root / "receipts" / "fill-idle-until-empty.json").is_file())


class AF2QueuePartialTests(unittest.TestCase):
    def test_note_queue_partial_writes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = note_queue_partial(
                root,
                stage="continue_handoff",
                error="boom handoff",
                shot_id="shot01",
                job_id="job-1",
            )
            self.assertTrue(path.is_file())
            row = read_json(path)
            self.assertEqual(row.get("kind"), "media-queue-partial")
            self.assertTrue(row.get("partial"))
            self.assertIn("honest_limits", row)
            note_queue_partial(root, stage="grok_take_sidecar", error="side fail", shot_id="shot01")
            row2 = read_json(path)
            self.assertEqual(len(row2.get("events") or []), 2)


class AF3AF6CloseoutTests(unittest.TestCase):
    def _plate_root(self, root: Path) -> None:
        out = root / "out"
        out.mkdir()
        plate = out / "film_final.mp4"
        plate.write_bytes(b"fake-plate")
        write_json(
            root / "manifest.json",
            {
                "gates": {"final_complete": True, "clips_complete": True},
                "outputs": {"final_film": {"path": str(plate)}},
            },
        )
        write_json(root / "film-spec.json", {"title": "af", "heat_scale": "soft", "scenes": []})

    def test_evidence_probe_fail_with_final_is_not_green(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._plate_root(root)

            def _boom(*_a, **_k):
                raise RuntimeError("probe exploded")

            with mock.patch(
                "caption_pixel_check.evidence_stale_after_final",
                side_effect=_boom,
            ):
                st = closeout_status(root)
            steps = {s["id"]: s for s in st["steps"]}
            self.assertFalse(steps["evidence_fresh"]["ok"])
            self.assertIn("probe", steps["evidence_fresh"]["detail"].lower())

    def test_post_doctor_hard_blocks_closeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._plate_root(root)
            fake_doctor = {
                "ok": False,
                "hard": [
                    {
                        "severity": "hard",
                        "code": "DUAL_TIMELINE_CLOCK",
                        "message": "clocks disagree",
                        "fix": 'aifilm timeline-clock rewrite --root "x"',
                    }
                ],
                "soft": [],
                "next_cmd": 'aifilm timeline-clock rewrite --root "x"',
            }
            with mock.patch("post_doctor.run_post_doctor", return_value=fake_doctor):
                st = closeout_status(root)
            steps = {s["id"]: s for s in st["steps"]}
            self.assertIn("post_doctor", steps)
            self.assertFalse(steps["post_doctor"]["ok"])
            self.assertIn("DUAL_TIMELINE_CLOCK", steps["post_doctor"].get("hard_codes") or [])

    def test_post_doctor_mix_partial_only_is_advisory_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._plate_root(root)
            fake_doctor = {
                "ok": True,
                "hard": [],
                "soft": [
                    {
                        "severity": "soft",
                        "code": "MIX_PARTIAL",
                        "message": "amix fallback",
                    }
                ],
                "next_cmd": None,
            }
            with mock.patch("post_doctor.run_post_doctor", return_value=fake_doctor):
                st = closeout_status(root)
            steps = {s["id"]: s for s in st["steps"]}
            self.assertTrue(steps["post_doctor"]["ok"])
            self.assertTrue(steps["post_doctor"].get("advisory"))
            self.assertTrue(steps["post_doctor"].get("mix_partial"))


class AF4TtsPartialTests(unittest.TestCase):
    def test_fallback_writes_tts_partial_receipt(self) -> None:
        import tts_backend

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out2 = root / "line2.mp3"

            def raise_minimax(*_a, **_k):
                raise tts_backend.TTSError("minimax down")

            def ok_edge(*_a, **_k):
                out2.write_bytes(b"ID3ok")

            with mock.patch.object(
                tts_backend,
                "probe",
                return_value={
                    "active": "minimax",
                    "backends": {"minimax": True, "edge": True, "voicebox": False},
                    "voicebox_profile": None,
                },
            ):
                with mock.patch.object(tts_backend, "assert_voice_backend_compatible"):
                    with mock.patch.object(
                        tts_backend, "normalize_performance_cue", return_value={}
                    ):
                        with mock.patch.object(
                            tts_backend,
                            "compile_edge",
                            return_value={
                                "text": "hi",
                                "rate": "+0%",
                                "volume": "+0%",
                                "pitch": "+0Hz",
                            },
                        ):
                            with mock.patch.object(tts_backend, "cue_hash", return_value="h"):
                                with mock.patch.object(
                                    tts_backend, "compile_instruction", return_value=""
                                ):
                                    with mock.patch.object(
                                        tts_backend, "minimax_model", return_value="m"
                                    ):
                                        with mock.patch.object(
                                            tts_backend, "fish_model", return_value=None
                                        ):
                                            with mock.patch.object(
                                                tts_backend,
                                                "tts_minimax",
                                                side_effect=raise_minimax,
                                            ):
                                                with mock.patch.object(
                                                    tts_backend, "tts_edge", side_effect=ok_edge
                                                ):
                                                    result = tts_backend.synthesize(
                                                        "你好世界",
                                                        out2,
                                                        backend="auto",
                                                        voice="zh-CN-XiaoxiaoNeural",
                                                        allow_network_fallback=True,
                                                        usage_root=root,
                                                    )
            self.assertIn("fallback", str(result.get("backend")).lower())
            self.assertTrue(result.get("partial"))
            receipt = root / "receipts" / "tts-partial.json"
            self.assertTrue(receipt.is_file())
            body = read_json(receipt)
            self.assertEqual(body.get("kind"), "tts-partial")
            self.assertTrue(body.get("partial"))
            self.assertIn("honest_limits", body)


class AF8DocDriftTests(unittest.TestCase):
    def test_hard_defaults_hero_bulk_h3_primary(self) -> None:
        path = Path(__file__).resolve().parents[1] / "references" / "hard-defaults.md"
        text = path.read_text(encoding="utf-8")
        self.assertIn("h3_primary", text)
        self.assertNotIn("hero bulk 按 Grok image_to_video → FRW API I2V", text)


if __name__ == "__main__":
    unittest.main()
