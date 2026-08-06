"""W3b RED→GREEN: export_cues.expand_cues_phrase_split calls
format_caption_lines (defined in export_composition) without importing it →
NameError at runtime. Fix with a function-local lazy import to avoid the
module-level circular dependency (export_composition imports export_cues).
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from post.export_cues import expand_cues_phrase_split  # noqa: E402


def test_single_phrase_cue_no_internal_error() -> None:
    cues = [
        {"start": 0.0, "end": 2.0, "zh": "深夜的展厅落锁了", "shot_id": "s1"},
    ]
    out = expand_cues_phrase_split(cues)
    assert isinstance(out, list)
    assert out
    assert "text" in out[0]


def test_multi_phrase_cue_splits_with_text() -> None:
    cues = [
        {"start": 0.0, "end": 6.0, "zh": "第一句短旁白。第二句也短。第三句收尾。", "shot_id": "s1"},
    ]
    out = expand_cues_phrase_split(cues)
    assert isinstance(out, list)
    assert len(out) >= 3
    assert all("text" in c for c in out)


def test_dual_language_cue_keeps_en_on_first() -> None:
    cues = [
        {"start": 0.0, "end": 4.0, "zh": "展厅落锁", "en": "Exhibition locked", "mode": "zh_en"},
    ]
    out = expand_cues_phrase_split(cues)
    assert isinstance(out, list)
    assert out
    first = out[0]
    assert first["en"]
    assert first["mode"] in {"zh_en", "zh"}