"""Unit tests for Plate 9: Sub-Sentence Forced Phoneme Alignment System.

Verifies:
1. subtitle_dialogue_alignment.py align_sub_sentence_phonemes character-weighted interpolation.
2. subtitle_dialogue_alignment.py align_sub_sentence_phonemes boundary receipt parsing.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from subtitle_dialogue_alignment import align_sub_sentence_phonemes  # noqa: E402


class PhonemeAlignmentTests(unittest.TestCase):
    def test_align_sub_sentence_phonemes_weighted(self) -> None:
        text = "等一下，不要走。"
        aligned = align_sub_sentence_phonemes(text, 4.0, start_offset_sec=1.0)

        self.assertEqual(len(aligned), 2)
        self.assertEqual(aligned[0]["text"], "等一下，")
        self.assertEqual(aligned[0]["start"], 1.0)
        self.assertEqual(aligned[1]["text"], "不要走。")
        self.assertEqual(aligned[1]["end"], 5.0)

    def test_align_sub_sentence_phonemes_boundary_receipts(self) -> None:
        text = "你好 世界"
        receipts = [
            {"word": "你好", "start": 0.0, "end": 1.2},
            {"word": "世界", "start": 1.2, "end": 2.5},
        ]
        aligned = align_sub_sentence_phonemes(
            text, 2.5, boundary_receipts=receipts, start_offset_sec=0.5
        )

        self.assertEqual(len(aligned), 2)
        self.assertEqual(aligned[0]["start"], 0.5)
        self.assertEqual(aligned[0]["end"], 1.7)
        self.assertEqual(aligned[1]["start"], 1.7)
        self.assertEqual(aligned[1]["end"], 3.0)


if __name__ == "__main__":
    unittest.main()
