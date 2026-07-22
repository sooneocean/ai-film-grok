"""TTS rehearsal receipt binding (offline register path — no network)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from tts_rehearsal import (  # noqa: E402
    TTSRehearsalError,
    load_rehearsal_receipt,
    measured_vo_by_shot,
    register_measured_durations,
    run_rehearsal,
)


def _minimal_spec() -> dict:
    return {
        "title": "tts-rehearsal-test",
        "vo_mode": "storyteller",
        "tts_backend": "edge",
        "director_intent": {
            "logline": "雨夜后座升温的完整承诺句。",
            "tone": "测试",
            "emotional_arc": ["a", "b", "c"],
        },
        "scenes": [
            {
                "shots": [
                    {
                        "id": "shot01",
                        "dramatic_function": "hook",
                        "nar": "话说她眨眼。",
                        "duration_sec": 6,
                        "dsl": {
                            "subject": "a",
                            "action": "blinks",
                            "motion": "soft blink, breath, idle not speaking",
                            "framing": ("medium, full head, headroom, safe framing no cropping"),
                        },
                    },
                    {
                        "id": "shot02",
                        "dramatic_function": "action",
                        "nar": "话说她落锁。",
                        "duration_sec": 6,
                        "dsl": {
                            "subject": "a",
                            "action": "locks",
                            "motion": "hand turns latch, idle not speaking",
                            "framing": (
                                "medium full, full head, headroom, safe framing no cropping"
                            ),
                        },
                    },
                ]
            }
        ],
    }


@pytest.mark.slow
class TTSRehearsalTests(unittest.TestCase):
    @pytest.mark.slow
    def test_register_measured_durations_writes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = register_measured_durations(
                root,
                [
                    {
                        "shot_id": "shot01",
                        "measured_duration_sec": 2.4,
                        "est_vo_sec": 2.0,
                        "duration_sec": 6.0,
                        "nar": "话说她眨眼。",
                    },
                    {
                        "shot_id": "shot02",
                        "measured_duration_sec": 3.1,
                        "est_vo_sec": 2.5,
                        "duration_sec": 6.0,
                    },
                ],
                source="register",
                backend="edge",
            )
            self.assertTrue(receipt["ok"])
            self.assertEqual(receipt["shot_count"], 2)
            self.assertEqual(receipt["evidence_class"], "executed_audio")
            path = root / "receipts" / "tts-rehearsal.json"
            self.assertTrue(path.is_file())
            loaded = load_rehearsal_receipt(root)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            ids = {s["shot_id"] for s in loaded["shots"]}
            self.assertEqual(ids, {"shot01", "shot02"})
            measured = measured_vo_by_shot(root)
            self.assertAlmostEqual(measured["shot01"], 2.4)
            self.assertAlmostEqual(measured["shot02"], 3.1)

    @pytest.mark.slow
    def test_register_rejects_missing_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(TTSRehearsalError):
                register_measured_durations(
                    root,
                    [{"shot_id": "shot01"}],  # no path, no duration
                )

    @pytest.mark.slow
    def test_run_rehearsal_register_map_with_real_audio(self) -> None:
        if not __import__("shutil").which("ffmpeg"):
            self.skipTest("ffmpeg not available")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(
                json.dumps(_minimal_spec(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            audio_dir = root / "audio"
            audio_dir.mkdir()
            paths: dict[str, Path] = {}
            for sid, dur in (("shot01", 0.4), ("shot02", 0.55)):
                wav = audio_dir / f"{sid}.wav"
                subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        f"sine=frequency=440:duration={dur}",
                        "-ar",
                        "16000",
                        str(wav),
                    ],
                    check=True,
                    capture_output=True,
                )
                paths[sid] = wav
            receipt = run_rehearsal(
                root,
                register_map=paths,
                synthesize=False,
            )
            self.assertTrue(receipt["ok"])
            self.assertEqual(receipt["source"], "register")
            by_id = {s["shot_id"]: s for s in receipt["shots"]}
            self.assertIn("shot01", by_id)
            self.assertIn("shot02", by_id)
            self.assertGreater(by_id["shot01"]["measured_duration_sec"], 0.2)
            self.assertGreater(by_id["shot02"]["measured_duration_sec"], 0.3)
            # CLI entry exists
            from aifilm_grok import build_parser

            p = build_parser()
            # ensure subcommand registered
            # argparse stores subparsers; smoke via parse
            args = p.parse_args(
                [
                    "tts-rehearse",
                    "--root",
                    str(root),
                    "--register-json",
                    str(self._write_reg(root, paths)),
                    "--no-synthesize",
                ]
            )
            self.assertEqual(args.cmd, "tts-rehearse")

    def _write_reg(self, root: Path, paths: dict[str, Path]) -> Path:
        reg = root / "reg.json"
        reg.write_text(
            json.dumps(
                [{"shot_id": sid, "path": str(p)} for sid, p in paths.items()],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return reg


class TTSRehearsalTimingGateTests(unittest.TestCase):
    """Measured VO must change real preflight / production_gates outcomes."""

    def _seed_short_nar_root(self, root: Path, *, duration_sec: float = 6.0) -> None:
        """Short nar → estimate fits plate; measured can still over-plate."""
        (root / "receipts").mkdir(parents=True, exist_ok=True)
        (root / "manifest.json").write_text(
            json.dumps(
                {"schema_version": 1, "gates": {}, "clips": {}, "outputs": {}},
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        (root / "style-bible.json").write_text(
            json.dumps({"locked": True, "identity_lock": "ok"}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        # ~6 chars → est_vo ≈ 1.5s — passes estimate vo_pacing for 6s plate
        spec = {
            "title": "measured-gate",
            "vo_mode": "storyteller",
            "tts_backend": "edge",
            "director_intent": {
                "logline": "雨夜后座升温的完整承诺句。",
                "tone": "测试",
                "emotional_arc": ["a", "b", "c"],
            },
            "sound_plan": {"mood": "rnb"},
            "scenes": [
                {
                    "shots": [
                        {
                            "id": "shot01",
                            "dramatic_function": "hook",
                            "nar": "话说她眨眼。",
                            "duration_sec": duration_sec,
                            "dsl": {
                                "subject": "a",
                                "action": "blinks",
                                "motion": "soft blink, breath, idle not speaking",
                                "framing": (
                                    "medium, full head, headroom, safe framing no cropping"
                                ),
                            },
                        }
                    ]
                }
            ],
        }
        (root / "film-spec.json").write_text(
            json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    @pytest.mark.slow
    def test_estimate_only_preflight_ok_without_receipt(self) -> None:
        from preflight import run_preflight

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_short_nar_root(root)
            report = run_preflight(root)
            codes = {i["code"] for i in report["hard"]}
            self.assertNotIn("tts_rehearsal_over_plate", codes)
            # short nar should not trip loop_risk either
            self.assertNotIn("loop_risk", codes)

    @pytest.mark.slow
    def test_over_plate_measured_fails_preflight(self) -> None:
        """Real preflight path: short nar (estimate ok) + measured 8s > 6s plate → hard."""
        from preflight import run_preflight

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_short_nar_root(root, duration_sec=6.0)
            # Register measured far over plate (no network)
            register_measured_durations(
                root,
                [
                    {
                        "shot_id": "shot01",
                        "measured_duration_sec": 8.0,
                        "est_vo_sec": 1.5,
                        "duration_sec": 6.0,
                        "nar": "话说她眨眼。",
                    }
                ],
                source="register",
            )
            report = run_preflight(root)
            codes = {i["code"] for i in report["hard"]}
            self.assertIn("tts_rehearsal_over_plate", codes)
            self.assertFalse(report["hard_ok"])
            timing = report.get("tts_timing") or {}
            self.assertTrue(timing.get("present"))
            self.assertIn("shot01", timing.get("over_plate_shots") or [])
            # per_shot must prefer measured source
            per = {p["shot_id"]: p for p in (timing.get("per_shot") or [])}
            self.assertEqual(per["shot01"]["source"], "measured")
            self.assertGreaterEqual(per["shot01"]["vo_sec"], 7.9)

    @pytest.mark.slow
    def test_over_plate_measured_fails_assert_no_loop_risk(self) -> None:
        """production_gates final path: measured over-plate hard even if estimate short."""
        from production_gates import ProductionGateError, assert_no_loop_risk

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_short_nar_root(root)
            register_measured_durations(
                root,
                [
                    {
                        "shot_id": "shot01",
                        "measured_duration_sec": 9.0,
                        "est_vo_sec": 1.5,
                        "duration_sec": 6.0,
                    }
                ],
            )
            with self.assertRaises(ProductionGateError) as ctx:
                assert_no_loop_risk(root, force=False)
            msg = str(ctx.exception).lower()
            self.assertTrue(
                "measured" in msg or "tts rehearsal" in msg or "over" in msg,
                msg,
            )
            # allow_loop_risk (force=True) still must not skip measured over-plate
            with self.assertRaises(ProductionGateError) as ctx2:
                assert_no_loop_risk(root, force=True)
            self.assertIn("measured", str(ctx2.exception).lower())

    @pytest.mark.slow
    def test_strict_missing_receipt_fails_assert(self) -> None:
        from production_gates import ProductionGateError, assert_tts_rehearsal_timing

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_short_nar_root(root)
            with self.assertRaises(ProductionGateError) as ctx:
                assert_tts_rehearsal_timing(root, strict=True)
            self.assertIn("missing", str(ctx.exception).lower())

    @pytest.mark.slow
    def test_loop_risk_prefers_measured_over_estimate(self) -> None:
        """loop_risk_shots_from_spec uses measured when map provided."""
        from production_gates import loop_risk_shots_from_spec

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_short_nar_root(root)
            spec = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            # estimate path: short nar → no risk
            self.assertEqual(loop_risk_shots_from_spec(spec), [])
            # measured path: 7s on 6s plate → risk
            risk = loop_risk_shots_from_spec(spec, measured_by_shot={"shot01": 7.0})
            self.assertIn("shot01", risk)


if __name__ == "__main__":
    unittest.main()
