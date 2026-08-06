"""P4-1: first unit tests for final.render_defaults constants."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from final import render_defaults as D  # noqa: E402


def test_mix_defaults_are_sane() -> None:
    assert 0 < D.DEFAULT_MUSIC_VOLUME < 1
    assert 0 < D.DEFAULT_BGM_GEN_AMP < 1
    assert D.DEFAULT_VO_GAIN > 0
    assert D.SR == 44100
    assert D.DEFAULT_SUB_MAX_CHARS >= 8
