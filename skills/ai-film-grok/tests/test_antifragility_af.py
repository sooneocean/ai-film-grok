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


def _impl_source(module_filename: str) -> Path:
    """Resolve real implementation for W6 hard-compat shims (media./audio./post.)."""
    path = SCRIPTS / module_filename
    text = path.read_text(encoding="utf-8")
    if "sys.modules[__name__]" in text or "Shim —" in text or 'as _impl' in text:
        for pkg in ("media", "audio", "post", "narrative", "spine", "gates", "plan"):
            candidate = SCRIPTS / pkg / module_filename
            if candidate.is_file() and candidate.stat().st_size > 200:
                return candidate
    return path


class AF1SubprocessTimeoutTests(unittest.TestCase):
    def test_util_run_timeout_raises(self) -> None:
        with self.assertRaises(subprocess.TimeoutExpired):
            util_run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2)

    def test_h3_soft_identity_midframe_has_timeout(self) -> None:
        src = _impl_source("h3_fill_idle.py").read_text(encoding="utf-8")
        self.assertIn("timeout=30", src)
        self.assertIn("identity_midframe_timeout_or_fail", src)
        # midframe path must not use bare subprocess without timeout
        block = src.split("def _soft_identity_penalty")[1].split("def score_take_for_pk")[0]
        self.assertIn("util_run", block)
        self.assertIn("timeout=30", block)

    def test_soft_identity_timeout_soft_skips_penalty(self) -> None:
        """AF1 · TimeoutExpired on midframe extract → caution, not process hang."""
        from h3_fill_idle import _soft_identity_penalty

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            still = root / "stills"
            still.mkdir()
            (still / "s1.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
            take = root / "takes" / "s1"
            take.mkdir(parents=True)
            clip = take / "h3_t1.mp4"
            clip.write_bytes(b"\x00" * 1024)

            def _boom(*_a, **_k):
                raise subprocess.TimeoutExpired(cmd=["ffmpeg"], timeout=30)

            with (
                mock.patch("h3_workflow._approved_still", return_value=still / "s1.png"),
                mock.patch("shutil.which", return_value="/usr/bin/ffmpeg"),
                mock.patch("util.subprocess.run", side_effect=_boom),
            ):
                pen, caut = _soft_identity_penalty(root, "s1", str(clip), lane="h3")
            self.assertIn("identity_midframe_timeout_or_fail", caut)
            self.assertTrue(all(not c.startswith("identity_l1_") for c in caut))

    def test_scene_sound_ffmpeg_paths_have_timeout(self) -> None:
        src = _impl_source("scene_sound_stems.py").read_text(encoding="utf-8")
        self.assertIn("timeout=120", src)
        self.assertIn("timeout=180", src)
        runs = src.split("subprocess.run(")[1:]
        ffmpeg_runs = [c for c in runs if '"ffmpeg"' in c[:800] or "'ffmpeg'" in c[:800]]
        self.assertGreaterEqual(len(ffmpeg_runs), 2)
        for chunk in ffmpeg_runs:
            self.assertIn("timeout=", chunk[:1200])


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
                    i_own_the_gpu=True,
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



class Wave3ShortformTimeoutTests(unittest.TestCase):
    def test_shortform_decode_probe_have_timeout(self) -> None:
        src = _impl_source("shortform_motion.py").read_text(encoding="utf-8")
        self.assertIn("timeout=60", src)
        self.assertIn("timeout=30", src)
        self.assertIn("local motion candidate decode timed out", src)
        self.assertIn("local motion candidate probe timed out", src)


class Wave3H3WorkflowTimeoutTests(unittest.TestCase):
    """R-util / R-af1 · h3_workflow ffmpeg + register-clip must not hang forever."""

    def test_h3_workflow_subprocess_runs_have_timeout(self) -> None:
        src = _impl_source("h3_workflow.py").read_text(encoding="utf-8")
        self.assertIn("timeout=120", src)  # strip stream-copy
        self.assertIn("timeout=300", src)  # strip re-encode + register-clip
        self.assertIn("timeout=600", src)  # geometry upscale
        # volumedetect moved to core.media_ops (timeout=60) — still soft-fail path
        self.assertIn("timeout=60", src)
        self.assertIn("volumedetect_timeout", src)
        runs = src.split("subprocess.run(")[1:]
        # 5 direct runs remain after volume probe extraction to media_ops
        self.assertGreaterEqual(len(runs), 5)
        for chunk in runs:
            self.assertIn("timeout=", chunk[:1600], msg=chunk[:200])
        self.assertIn("timed out", src)

    def test_continue_handoff_endframe_has_timeout(self) -> None:
        src = _impl_source("continue_handoff.py").read_text(encoding="utf-8")
        self.assertIn("timeout=60", src)
        runs = src.split("subprocess.run(")[1:]
        self.assertGreaterEqual(len(runs), 1)
        for chunk in runs:
            self.assertIn("timeout=", chunk[:1200])

    def test_native_audio_volumedetect_timeout_soft(self) -> None:
        from h3_workflow import _native_audio_usable

        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "t.mp4"
            clip.write_bytes(b"\x00" * 64)

            with (
                mock.patch(
                    "media_qa.analyze_media",
                    return_value={"has_audio": True, "ok": True},
                ),
                mock.patch(
                    "core.media_ops.probe_native_audio_mean_volume",
                    side_effect=TimeoutError("volumedetect timed out after 60s"),
                ),
            ):
                usable, meta = _native_audio_usable(clip)
            self.assertTrue(usable)
            self.assertTrue(meta.get("volume_probe_timeout"))
            self.assertEqual(meta.get("usable_reason"), "volumedetect_timeout")

class Wave3AudioPipelineTimeoutTests(unittest.TestCase):
    """R-af1 residual · TTS render / event voice stem / delivery gate must bound hangs."""

    def test_audio_tts_render_subprocess_runs_have_timeout(self) -> None:
        src = _impl_source("audio_tts_render.py").read_text(encoding="utf-8")
        self.assertIn("timeout=30", src)  # ffprobe duration
        self.assertIn("timeout=120", src)  # mp3→wav
        runs = src.split("subprocess.run(")[1:]
        self.assertGreaterEqual(len(runs), 2)
        for chunk in runs:
            self.assertIn("timeout=", chunk[:1200], msg=chunk[:200])
        self.assertIn("timed out", src)

    def test_event_voice_stem_subprocess_runs_have_timeout(self) -> None:
        src = _impl_source("event_voice_stem.py").read_text(encoding="utf-8")
        self.assertIn("timeout=180", src)  # decode
        self.assertIn("timeout=120", src)  # write stem
        runs = src.split("subprocess.run(")[1:]
        self.assertGreaterEqual(len(runs), 2)
        for chunk in runs:
            self.assertIn("timeout=", chunk[:1200], msg=chunk[:200])
        self.assertIn("timed out", src)

    def test_audio_delivery_gate_probe_has_timeout(self) -> None:
        src = _impl_source("audio_delivery_gate.py").read_text(encoding="utf-8")
        self.assertIn("timeout=30", src)
        runs = src.split("subprocess.run(")[1:]
        self.assertGreaterEqual(len(runs), 1)
        for chunk in runs:
            self.assertIn("timeout=", chunk[:800], msg=chunk[:200])
        self.assertIn("ffprobe timed out", src)

    def test_audio_tts_duration_timeout_raises(self) -> None:
        from audio_tts_render import AudioTTSRenderError, _duration

        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "x.wav"
            wav.write_bytes(b"\x00" * 32)

            def _boom(*_a, **_k):
                raise subprocess.TimeoutExpired(cmd=["ffprobe"], timeout=30)

            with mock.patch("audio_tts_render.subprocess.run", side_effect=_boom):
                with self.assertRaises(AudioTTSRenderError) as ctx:
                    _duration(wav)
            self.assertIn("timed out", str(ctx.exception))

    def test_shortform_director_ffmpeg_paths_have_timeout(self) -> None:
        src = _impl_source("shortform_director.py").read_text(encoding="utf-8")
        self.assertIn("timeout=180", src)
        self.assertIn("timeout=300", src)
        self.assertIn("timeout=30", src)
        runs = src.split("subprocess.run(")[1:]
        self.assertGreaterEqual(len(runs), 4)
        for chunk in runs:
            self.assertIn("timeout=", chunk[:1600], msg=chunk[:200])
        self.assertIn("timed out", src)

    def test_burn_srt_pil_ffmpeg_has_timeout(self) -> None:
        src = _impl_source("burn_srt_pil.py").read_text(encoding="utf-8")
        self.assertIn("timeout=1800", src)

    def test_narrative_evidence_probe_has_timeout(self) -> None:
        src = _impl_source("narrative_evidence.py").read_text(encoding="utf-8")
        self.assertIn("timeout=30", src)



class Wave3AdapterNodeTimeoutTests(unittest.TestCase):
    """R-af1 residual · adapters + lipsync node + canary/opt probe hangs."""

    def test_elevenlabs_and_voicebox_ffmpeg_have_timeout(self) -> None:
        el = (SCRIPTS / "adapters" / "elevenlabs_tts.py").read_text(encoding="utf-8")
        vb = (SCRIPTS / "adapters" / "voicebox_tts.py").read_text(encoding="utf-8")
        mu = (SCRIPTS / "adapters" / "music_external.py").read_text(encoding="utf-8")
        hg = (SCRIPTS / "adapters" / "higgs_audio.py").read_text(encoding="utf-8")
        self.assertIn("timeout=120", el)
        self.assertIn("timeout=120", vb)
        self.assertIn("timeout=300", mu)
        self.assertIn("timeout=1800", hg)

    def test_node_lipsync_adapters_have_timeout(self) -> None:
        # v2.40: post lipsync adapters are tombstones (no live subprocess).
        ls = (SCRIPTS / "node" / "latentsync_adapter.py").read_text(encoding="utf-8")
        mt = (SCRIPTS / "node" / "musetalk_adapter.py").read_text(encoding="utf-8")
        self.assertIn("Tombstone", ls)
        self.assertIn("Tombstone", mt)
        self.assertIn("LipSyncError", ls)
        self.assertIn("LipSyncError", mt)

    def test_mmaudio_run_checked_defaults_timeout(self) -> None:
        src = _impl_source("mmaudio_adapter.py").read_text(encoding="utf-8")
        self.assertIn('setdefault("timeout", 1800)', src)
        self.assertIn("TimeoutExpired", src)

    def test_elevenlabs_canary_metrics_have_timeout(self) -> None:
        src = _impl_source("elevenlabs_canary.py").read_text(encoding="utf-8")
        self.assertIn("timeout=30", src)
        self.assertIn("timeout=60", src)
        # Shipped path: two subprocess.run (ffprobe + silencedetect) plus
        # probe_native_audio_mean_volume(..., timeout=60.0) for mean volume.
        runs = src.split("subprocess.run(")[1:]
        self.assertGreaterEqual(len(runs), 2)
        for chunk in runs:
            if "ffprobe" in chunk[:400] or "ffmpeg" in chunk[:400] or "volumedetect" in chunk[:800] or "silencedetect" in chunk[:800]:
                self.assertIn("timeout=", chunk[:1200])
        self.assertIn("probe_native_audio_mean_volume", src)
        self.assertIn("timeout=60.0", src)

    def test_optimization_program_probe_has_timeout(self) -> None:
        src = _impl_source("optimization_program.py").read_text(encoding="utf-8")
        self.assertIn("timeout=30", src)


if __name__ == "__main__":
    unittest.main()
