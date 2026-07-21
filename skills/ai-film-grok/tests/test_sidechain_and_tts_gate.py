"""Phase E: sidechain resolve + Edge Neural vs external TTS hard gate."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from preflight import run_preflight  # noqa: E402
from sound_plan import (  # noqa: E402
    SIDECHAIN_DEFAULT,
    SIDECHAIN_RNB,
    resolve_sidechain,
    sidechain_filter_fragment,
)
from tts_backend import (  # noqa: E402
    TTSError,
    assert_voice_backend_compatible,
    is_edge_neural_voice_id,
)


class SidechainTests(unittest.TestCase):
    def test_rnb_preset_longer_release(self) -> None:
        sc = resolve_sidechain(None, mood="rnb")
        self.assertEqual(sc["release_ms"], SIDECHAIN_RNB["release_ms"])
        self.assertGreater(sc["release_ms"], SIDECHAIN_DEFAULT["release_ms"])

    def test_warm_uses_default(self) -> None:
        sc = resolve_sidechain({"mood": "warm"}, mood="warm")
        self.assertEqual(sc["release_ms"], SIDECHAIN_DEFAULT["release_ms"])

    def test_plan_sidechain_override(self) -> None:
        sc = resolve_sidechain(
            {"mood": "rnb", "sidechain": {"release_ms": 900, "ratio": 4.0}},
            mood="rnb",
        )
        self.assertEqual(sc["release_ms"], 900.0)
        self.assertEqual(sc["ratio"], 4.0)

    def test_cli_overrides_win(self) -> None:
        sc = resolve_sidechain(
            {"mood": "rnb", "sidechain": {"release_ms": 900}},
            mood="rnb",
            overrides={"release_ms": 1000, "threshold": 0.05},
        )
        self.assertEqual(sc["release_ms"], 1000.0)
        self.assertEqual(sc["threshold"], 0.05)

    def test_filter_fragment(self) -> None:
        frag = sidechain_filter_fragment(SIDECHAIN_RNB)
        self.assertIn("sidechaincompress=", frag)
        self.assertIn("release=720", frag)


class TtsNeuralGateTests(unittest.TestCase):
    def test_detect_neural(self) -> None:
        self.assertTrue(is_edge_neural_voice_id("zh-CN-XiaoxiaoNeural"))
        self.assertTrue(is_edge_neural_voice_id("zh-CN-YunxiNeural"))
        self.assertFalse(is_edge_neural_voice_id("21m00Tcm4TlvDq8ikWAM"))
        self.assertFalse(is_edge_neural_voice_id(""))

    def test_external_rejects_neural(self) -> None:
        with self.assertRaises(TTSError) as ctx:
            assert_voice_backend_compatible("external", "zh-CN-XiaoxiaoNeural")
        self.assertIn("Neural", str(ctx.exception))

    def test_edge_allows_neural(self) -> None:
        assert_voice_backend_compatible("edge", "zh-CN-XiaoxiaoNeural")

    def test_auto_with_tts_argv_rejects_neural(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"AIFILM_TTS_ARGV": '["python","elevenlabs_tts.py"]'},
            clear=False,
        ):
            with self.assertRaises(TTSError):
                assert_voice_backend_compatible("auto", "zh-CN-YunxiNeural")

    def test_preflight_hard_on_neural_external(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            import json

            man = {
                "schema_version": 1,
                "gates": {},
                "clips": {},
                "outputs": {},
            }
            (root / "manifest.json").write_text(
                json.dumps(man), encoding="utf-8"
            )
            (root / "style-bible.json").write_text(
                json.dumps({"locked": True, "identity_lock": "x" * 20}),
                encoding="utf-8",
            )
            spec = {
                "title": "tts-gate",
                "vo_mode": "storyteller",
                "tts_backend": "external",
                "vo_voice": "zh-CN-XiaoxiaoNeural",
                "director_intent": {
                    "logline": "测试 TTS Neural 外置后端硬门禁的完整句。",
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
                                    "action": "b",
                                    "motion": "slow push-in, soft blink, idle not speaking",
                                },
                            }
                        ]
                    }
                ],
            }
            (root / "film-spec.json").write_text(
                json.dumps(spec, ensure_ascii=False), encoding="utf-8"
            )
            report = run_preflight(root)
            codes = {i["code"] for i in report["hard"]}
            self.assertIn("tts_neural_on_external", codes)
            self.assertFalse(report["hard_ok"])


if __name__ == "__main__":
    unittest.main()
