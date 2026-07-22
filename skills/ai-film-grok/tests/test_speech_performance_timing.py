from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from speech_performance_timing import build_speech_performance_timing  # noqa: E402


class SpeechPerformanceTimingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "receipts" / "reviews").mkdir(parents=True)
        (self.root / "film-spec.json").write_text(
            json.dumps(
                {
                    "content_channels_strict": True,
                    "scenes": [
                        {
                            "shots": [
                                {
                                    "id": "shot01",
                                    "lipsync": True,
                                    "content_channels": {
                                        "voice": {
                                            "kind": "dialogue",
                                            "text": "别走。",
                                            "on_camera": True,
                                        }
                                    },
                                }
                            ]
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.root / "timeline.json").write_text(
            json.dumps({"shots": [{"id": "shot01", "duration_sec": 3.0}]}), encoding="utf-8"
        )
        (self.root / "receipts" / "tts-rehearsal.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "shots": [
                        {
                            "shot_id": "shot01",
                            "measured_duration_sec": 1.2,
                            "text_kind": "dialogue",
                            "text": "别走。",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _review(self, delivery_end: float) -> None:
        (self.root / "receipts" / "reviews" / "shot01.json").write_text(
            json.dumps(
                {
                    "performance_contract": {
                        "evidence": {
                            "dialogue_delivery": {
                                "timestamp_sec": delivery_end,
                                "note": "最后一个音节结束后口型停住",
                            }
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @pytest.mark.slow
    def test_accepts_measured_dialogue_end_with_reaction_space(self) -> None:
        self._review(1.5)
        report = build_speech_performance_timing(self.root)
        self.assertTrue(report["ok"], report)
        self.assertTrue(Path(report["path"]).is_file())

    @pytest.mark.slow
    def test_rejects_cut_before_audio_end_and_missing_breathing_room(self) -> None:
        self._review(1.0)
        report = build_speech_performance_timing(self.root)
        self.assertFalse(report["ok"])
        self.assertIn("DIALOGUE_CUTS_BEFORE_AUDIO_END", {item["code"] for item in report["errors"]})
        self._review(2.95)
        report = build_speech_performance_timing(self.root)
        self.assertIn(
            "DIALOGUE_REACTION_SPACE_MISSING", {item["code"] for item in report["errors"]}
        )

    @pytest.mark.slow
    def test_rejects_narration_or_text_mismatch_as_lipsync_measurement(self) -> None:
        self._review(1.5)
        path = self.root / "receipts" / "tts-rehearsal.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["shots"][0]["text_kind"] = "narration"
        data["shots"][0]["text"] = "旁白"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        report = build_speech_performance_timing(self.root)
        codes = {item["code"] for item in report["errors"]}
        self.assertIn("DIALOGUE_TTS_KIND_MISMATCH", codes)
        self.assertIn("DIALOGUE_TTS_TEXT_MISMATCH", codes)
