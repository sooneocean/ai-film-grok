"""P0 · 2026-07-24 ep2 lessons: narrator wins over nar_ja; SRT cues clamp non-overlap."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from render_final import (  # noqa: E402
    build_subtitle_cues_for_shots,
    is_character_speech_shot,
    spoken_text_for_shot,
    write_srt,
)


class VoiceLangAndSrtClampTests(unittest.TestCase):
    def test_storyteller_speaker_not_character_even_with_nar_ja(self) -> None:
        shot = {
            "speaker": "storyteller",
            "nar": "实验室高窗，夜色压城。",
            "nar_ja": "だめ…熱い…",  # stray field — must not flip track
        }
        self.assertFalse(is_character_speech_shot(shot))
        spoken = spoken_text_for_shot(
            shot,
            dialogue_spoken_lang="zh",
            narration_spoken_lang="zh",
            vo_mode="hybrid",
        )
        self.assertIn("实验室", spoken)
        self.assertNotIn("だめ", spoken)

    def test_heroine_uses_chinese_dialogue_not_legacy_ja(self) -> None:
        shot = {
            "speaker": "heroine",
            "nar": "她咬唇抑制，身体已经失控。",
            "dialogue": "别…我已经控制不住了。",
            "caption_text": "别…我已经控制不住了。",
            "nar_ja": "だめ…もう抑えられない…",  # retired field — ignored
        }
        self.assertTrue(is_character_speech_shot(shot))
        spoken = spoken_text_for_shot(
            shot,
            dialogue_spoken_lang="zh",
            narration_spoken_lang="zh",
            vo_mode="hybrid",
        )
        self.assertIn("控制不住", spoken)
        self.assertNotIn("だめ", spoken)

    def test_subtitle_cues_clamp_overlap(self) -> None:
        # Two dense units with positive sub_lead would previously overlap
        shot_audio = [
            {
                "target": 4.0,
                "raw_vo_dur": 4.0,
                "vo_dur": 4.0,
                "units": ["第一句很长的中文旁白。", "第二句立刻接上。"],
            }
        ]
        cues, _tl = build_subtitle_cues_for_shots(
            shot_audio,
            title_duration=0.0,
            end_duration=0.0,
            transition_sec=0.0,
            sub_lead=0.08,
            sub_min=0.48,
            sub_max=1.75,
            default_intent="hard",
        )
        self.assertGreaterEqual(len(cues), 2)
        for i in range(1, len(cues)):
            self.assertGreaterEqual(
                cues[i]["start"] + 1e-6,
                cues[i - 1]["end"],
                msg=f"cue {i} overlaps previous: {cues}",
            )

    def test_write_srt_accepts_clamped(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "t.srt"
            # deliberately overlapping input — write_srt must clamp
            write_srt(
                path,
                [
                    {"start": 0.0, "end": 1.5, "text": "甲"},
                    {"start": 1.2, "end": 2.0, "text": "乙"},
                ],
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("甲", text)
            self.assertIn("乙", text)


if __name__ == "__main__":
    unittest.main()
