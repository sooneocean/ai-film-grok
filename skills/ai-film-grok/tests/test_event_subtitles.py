from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from subtitle_srt import segments_to_srt_text


def test_explicit_cross_talk_srt_can_preserve_overlapping_event_windows():
    text = segments_to_srt_text(
        [
            {"start": 0.0, "end": 1.0, "text": "先说"},
            {"start": 0.5, "end": 1.5, "text": "打断"},
        ],
        allow_overlaps=True,
    )

    assert "先说" in text
    assert "打断" in text
