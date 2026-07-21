"""Phase F: write-spec pins edge + sidechain; status audio; storyteller soft."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import aifilm_grok  # noqa: E402
from film_spec import validate_film_spec  # noqa: E402
from preflight import run_preflight  # noqa: E402
from render_final import probe_mixed_loudness  # noqa: E402


def _minimal_spec(*, tts: str = "auto", tone: str = "色气·诱惑") -> dict:
    return {
        "title": "phase-f-test",
        "vo_mode": "storyteller",
        "tts_backend": tts,
        "director_intent": {
            "logline": "测试 write-spec 钉 edge 与侧链注入的完整句子。",
            "tone": tone,
            "emotional_arc": ["hook", "react", "end"],
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
                            "action": "looks",
                            "motion": "slow push-in, soft blink, idle not speaking",
                        },
                    }
                ]
            }
        ],
    }


class WriteSpecPinTests(unittest.TestCase):
    def test_storyteller_auto_becomes_edge(self) -> None:
        spec = _minimal_spec(tts="auto")
        validate_film_spec(spec, assign_missing_ids=False)
        self.assertEqual(spec["tts_backend"], "edge")
        self.assertTrue(any("edge" in n for n in (spec.get("_tts_notes") or [])))

    def test_explicit_minimax_kept(self) -> None:
        spec = _minimal_spec(tts="minimax")
        validate_film_spec(spec, assign_missing_ids=False)
        self.assertEqual(spec["tts_backend"], "minimax")

    def test_rnb_sidechain_injected(self) -> None:
        spec = _minimal_spec(tts="edge")
        validate_film_spec(spec, assign_missing_ids=False)
        sp = spec["sound_plan"]
        self.assertEqual(sp["mood"], "rnb")
        self.assertIn("sidechain", sp)
        self.assertGreaterEqual(float(sp["sidechain"]["release_ms"]), 700)


class StatusAudioTests(unittest.TestCase):
    def test_status_audio_summary_from_spec_and_mix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("audio", "receipts", "out", "clips", "canonical"):
                (root / name).mkdir()
            spec = _minimal_spec(tts="edge")
            validate_film_spec(spec, assign_missing_ids=False)
            (root / "film-spec.json").write_text(
                json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "title": "phase-f",
                        "gates": {},
                        "clips": {},
                        "outputs": {},
                    }
                ),
                encoding="utf-8",
            )
            (root / "audio" / "mix_report.json").write_text(
                json.dumps(
                    {
                        "mood": "rnb",
                        "sfx_overlay_count": 2,
                        "sidechain_applied": True,
                        "sidechain": {"release_ms": 720},
                        "loudness": {"ok": True, "integrated_lufs": -16.0},
                        "bed_source": "procedural",
                    }
                ),
                encoding="utf-8",
            )
            summary = aifilm_grok._status_audio_summary(root)
            self.assertEqual(summary["tts_backend"], "edge")
            self.assertEqual(summary["sound_plan_mood"], "rnb")
            self.assertEqual(summary["sfx_overlay_count"], 2)
            self.assertEqual(summary["loudness"]["integrated_lufs"], -16.0)


class PreflightStorytellerSoftTests(unittest.TestCase):
    def test_soft_when_storyteller_minimax(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            (root / "manifest.json").write_text(
                json.dumps({"schema_version": 1, "gates": {}, "clips": {}, "outputs": {}}),
                encoding="utf-8",
            )
            (root / "style-bible.json").write_text(
                json.dumps({"locked": True, "identity_lock": "x" * 20}),
                encoding="utf-8",
            )
            spec = _minimal_spec(tts="minimax")
            validate_film_spec(spec, assign_missing_ids=False)
            (root / "film-spec.json").write_text(
                json.dumps(spec, ensure_ascii=False), encoding="utf-8"
            )
            report = run_preflight(root)
            soft = {i["code"] for i in report["soft"]}
            self.assertIn("tts_storyteller_not_edge", soft)


class LoudnessProbeShapeTests(unittest.TestCase):
    def test_probe_missing_file_returns_none(self) -> None:
        self.assertIsNone(probe_mixed_loudness(Path("/no/such/mixed.wav")))


if __name__ == "__main__":
    unittest.main()
