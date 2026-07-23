"""Unit tests for style_lock (input-ref medium + cast locks)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import style_lock as sl  # noqa: E402


def test_infer_medium_explicit():
    assert sl.infer_medium(explicit="manhua") == "manhua"
    assert sl.infer_medium(explicit="anime") == "anime"
    assert sl.infer_medium(explicit="photoreal") == "photoreal"


def test_infer_medium_from_hint():
    assert sl.infer_medium(user_hint="要稳定像漫剧") == "manhua"
    assert sl.infer_medium(theme="二次元恋爱") == "anime"
    assert sl.infer_medium(theme="写实都市") == "photoreal"


def test_signature_long_enough():
    fp = sl.build_style_fingerprint("manhua", palette="neon teal", lighting="rim")
    sig = sl.build_signature_block("街角重逢", fp)
    assert len(sig) >= 40
    assert "NEVER switch medium" in sig


def test_cast_lock_tokens():
    cl = sl.build_cast_lock(
        "lushiran",
        display_name="陆时冉",
        face_notes="oval face mole left cheek",
        hair_lock="black updo NEVER blonde",
    )
    assert "oval face" in cl["identity_lock_tokens"]
    assert "black updo" in cl["hair_lock"]


def test_still_prefix_has_medium_and_identity():
    fp = sl.build_style_fingerprint("manhua")
    cl = {"lushiran": sl.build_cast_lock("lushiran", face_notes="face A")}
    prefix = sl.build_agent_still_prompt_prefix(fp, cl, cast_ids=["lushiran"])
    assert "MEDIUM LOCK" in prefix
    assert "IDENTITY lushiran" in prefix
    assert "image_edit" in prefix.lower() or "cast master" in prefix.lower()


def test_validate_bible_hard_on_placeholder():
    bible = {
        "signature_block": "x" * 50,
        "palette": "to be filled from theme",
        "identity_lock": "ok face",
        "cast_masters": {},
    }
    r = sl.validate_style_lock_bible(bible)
    assert not r["ok"]
    assert any("PALETTE" in h or "CAST" in h or "FINGERPRINT" in h for h in r["hard"])


def test_apply_plan_merges_cast_locks():
    fp = sl.build_style_fingerprint("semi_real", palette="warm night")
    plan = {
        "style_fingerprint": fp,
        "signature_block": sl.build_signature_block("t", fp),
        "identity_lock": "id tokens",
        "cast_locks": {
            "hero": sl.build_cast_lock("hero", face_notes="face", default_wardrobe="coat")
        },
        "at": "now",
        "ref_sha256": "abc",
        "agent_still_prompt_prefix": "PREFIX",
        "agent_i2v_prompt_prefix": "I2V",
    }
    bible: dict = {"palette": "to be filled"}
    out = sl.apply_plan_to_bible(bible, plan)
    assert out["style_fingerprint"]["medium_key"] == "semi_real"
    assert "hero" in out["cast_locks"]
    assert out["agent_still_prompt_prefix"] == "PREFIX"
    assert "to be filled" not in str(out.get("palette") or "").lower() or "locked" in str(
        out.get("palette")
    )


def test_recommend_stability():
    r = sl.recommend_medium_for_user_goal("人物稳定性很差 漫剧质感")
    assert r["recommended"] == "manhua"
