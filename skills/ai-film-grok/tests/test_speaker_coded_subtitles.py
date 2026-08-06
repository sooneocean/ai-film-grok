"""Unit tests for Plate 2: Speaker-Coded Kinetic Subtitles System.

Verifies:
1. subtitle_typesetter.py ASS header style definitions (Heroine, MaleLead, Storyteller, ClimaxKinetic).
2. resolve_cue_style speaker palette mapping.
3. Kinetic pop-in animation tag injection for exclamations and climax cues.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from subtitle_typesetter import ASS_HEADER, build_ass_cues, resolve_cue_style  # noqa: E402


class SpeakerCodedSubtitlesTests(unittest.TestCase):
    def test_ass_header_contains_speaker_styles(self) -> None:
        self.assertIn("Style: Heroine", ASS_HEADER)
        self.assertIn("Style: MaleLead", ASS_HEADER)
        self.assertIn("Style: Storyteller", ASS_HEADER)
        self.assertIn("Style: ClimaxKinetic", ASS_HEADER)

    def test_resolve_cue_style(self) -> None:
        self.assertEqual(resolve_cue_style({"speaker": "heroine"}), "Heroine")
        self.assertEqual(resolve_cue_style({"speaker": "male_hero"}), "MaleLead")
        self.assertEqual(resolve_cue_style({"speaker": "storyteller"}), "Storyteller")
        self.assertEqual(resolve_cue_style({"heat_phase": "climax"}), "ClimaxKinetic")

    def test_kinetic_pop_in_animation_injection(self) -> None:
        cues = [
            {"start": 0.0, "end": 2.0, "text": "等一下！", "speaker": "heroine"},
            {"start": 2.0, "end": 5.0, "text": "普通旁白叙事", "speaker": "storyteller"},
        ]
        ass_content = build_ass_cues(cues)

        # Cue 1 has exclamation '！' -> Kinetic animation tag & Heroine style
        self.assertIn("Dialogue: 0,0:00:00.00,0:00:02.00,Heroine", ass_content)
        self.assertIn(r"{\fscx120\fscy120\t(0,120,\fscx100\fscy100)}等一下！", ass_content)

        # Cue 2 has storyteller style
        self.assertIn("Dialogue: 0,0:00:02.00,0:00:05.00,Storyteller", ass_content)


if __name__ == "__main__":
    unittest.main()
