from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from subtitle_dialogue_alignment import build_subtitle_dialogue_alignment  # noqa: E402


class SubtitleDialogueAlignmentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "out").mkdir()
        (self.root / "receipts" / "reviews").mkdir(parents=True)
        shot = {
            "id": "shot01",
            "lipsync": True,
            "safe_area": {"subtitle_clear": True, "subject_clear": True},
            "content_channels": {"voice": {"kind": "dialogue", "text": "别走"}},
        }
        (self.root / "film-spec.json").write_text(
            json.dumps(
                {"content_channels_strict": True, "scenes": [{"shots": [shot]}]}, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        (self.root / "timeline.json").write_text(
            json.dumps({"shots": [{"id": "shot01", "duration_sec": 2}]}), encoding="utf-8"
        )
        (self.root / "receipts" / "reviews" / "shot01.json").write_text(
            json.dumps(
                {
                    "performance_contract": {
                        "evidence": {"dialogue_delivery": {"timestamp_sec": 1.2}}
                    }
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    @pytest.mark.slow
    def test_requires_cue_through_dialogue_end(self) -> None:
        (self.root / "out" / "final.srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,200\n别走\n", encoding="utf-8"
        )
        self.assertTrue(build_subtitle_dialogue_alignment(self.root)["ok"])
        (self.root / "out" / "final.srt").write_text(
            "1\n00:00:00,000 --> 00:00:00,900\n别走\n", encoding="utf-8"
        )
        report = build_subtitle_dialogue_alignment(self.root)
        self.assertIn("SUBTITLE_ENDS_BEFORE_DIALOGUE", {e["code"] for e in report["errors"]})

    def test_rejects_caption_outside_shot_or_dialogue_window(self) -> None:
        review_path = self.root / "receipts" / "reviews" / "shot01.json"
        review_path.write_text(
            json.dumps(
                {
                    "performance_contract": {
                        "evidence": {
                            "dialogue_delivery": {
                                "start_sec": 0.2,
                                "timestamp_sec": 1.2,
                            }
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        (self.root / "out" / "final.srt").write_text(
            "1\n00:00:00,100 --> 00:00:01,300\n别走\n", encoding="utf-8"
        )

        report = build_subtitle_dialogue_alignment(self.root)

        self.assertIn(
            "SUBTITLE_OUTSIDE_DIALOGUE_WINDOW",
            {error["code"] for error in report["errors"]},
        )
