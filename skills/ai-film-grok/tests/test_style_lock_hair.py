"""style_lock hair hard defaults (v2.40.5)."""

from __future__ import annotations

from style_lock import validate_style_lock_bible


def test_hair_lock_missing_hard():
    bible = {
        "medium": "manhua cel",
        "style_fingerprint": {"medium_key": "manhua"},
        "signature_block": "x" * 50,
        "palette": "warm skin gold",
        "identity_lock": "face locked",
        "cast_masters": {"heroine": "/tmp/h.png"},
        "cast_locks": {"heroine": {"identity_lock_tokens": "face only", "hair_lock": ""}},
    }
    rep = validate_style_lock_bible(bible)
    assert any(h.startswith("HAIR_LOCK_MISSING") for h in rep["hard"])
    assert rep["ok"] is False


def test_hair_lock_present_ok():
    bible = {
        "medium": "manhua cel",
        "style_fingerprint": {"medium_key": "manhua", "negative": "watermark text logo"},
        "signature_block": "x" * 50,
        "palette": "warm",
        "identity_lock": "face",
        "cast_masters": {"heroine": "/tmp/h.png"},
        "cast_locks": {
            "heroine": {
                "identity_lock_tokens": "face",
                "hair_lock": "black long hair match cast master; NEVER random recolor",
            }
        },
    }
    rep = validate_style_lock_bible(bible)
    assert not any(h.startswith("HAIR_LOCK_MISSING") for h in rep["hard"])
