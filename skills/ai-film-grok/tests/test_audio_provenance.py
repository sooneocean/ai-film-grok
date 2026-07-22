from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from audio_provenance import build_audio_provenance  # noqa: E402


class AudioProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "receipts").mkdir()
        (self.root / "audio").mkdir()
        self.rehearsal_audio = self.root / "dialogue.wav"
        self.rehearsal_audio.write_bytes(b"dialogue source")
        self.carrier = self.root / "audio" / "narration.wav"
        self.carrier.write_bytes(b"mixed carrier")
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
                                        "voice": {"kind": "dialogue", "text": "别走。"}
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
            json.dumps({"shots": [{"id": "shot01", "duration_sec": 2}]}), encoding="utf-8"
        )
        (self.root / "manifest.json").write_text(
            json.dumps(
                {"outputs": {"final_film": {"path": "out/final.mp4", "sha256": "final-hash"}}}
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_rehearsal(self, audio_hash: str | None) -> None:
        (self.root / "receipts" / "tts-rehearsal.json").write_text(
            json.dumps(
                {
                    "shots": [
                        {
                            "shot_id": "shot01",
                            "path": str(self.rehearsal_audio),
                            "audio_sha256": audio_hash,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

    @pytest.mark.slow
    def test_binds_dialogue_audio_carrier_and_final_delivery(self) -> None:
        self._write_rehearsal(hashlib.sha256(self.rehearsal_audio.read_bytes()).hexdigest())
        report = build_audio_provenance(self.root)
        self.assertTrue(report["ok"], report)
        self.assertEqual(
            report["dialogue_sources"][0]["audio_sha256"],
            report["dialogue_sources"][0]["receipt_audio_sha256"],
        )
        self.assertTrue(Path(report["path"]).is_file())

    @pytest.mark.slow
    def test_rejects_replaced_rehearsal_audio(self) -> None:
        self._write_rehearsal("old-hash")
        report = build_audio_provenance(self.root)
        self.assertFalse(report["ok"])
        self.assertIn("DIALOGUE_AUDIO_HASH_STALE", {item["code"] for item in report["errors"]})
