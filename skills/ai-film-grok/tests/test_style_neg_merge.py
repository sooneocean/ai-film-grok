"""GLOBAL_DEFAULT_NEGATIVE merge."""

from __future__ import annotations

from style_lock import (
    GLOBAL_DEFAULT_NEGATIVE,
    build_agent_still_prompt_prefix,
    merge_default_negative,
)


def test_merge_dedupes():
    out = merge_default_negative("watermark, text")
    assert "watermark" in out.lower()
    assert "logo" in out.lower()
    assert out.lower().count("watermark") == 1


def test_still_prefix_includes_global_neg():
    fp = {
        "medium": "manhua",
        "still_hint": "cel",
        "signature_extra": "x",
        "negative": "photoreal",
    }
    text = build_agent_still_prompt_prefix(fp, {})
    assert "--no" in text
    assert "watermark" in text.lower() or "logo" in text.lower()
    assert "photoreal" in text.lower()
    assert GLOBAL_DEFAULT_NEGATIVE
