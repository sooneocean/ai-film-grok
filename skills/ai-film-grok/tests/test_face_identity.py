"""Tests for pixel face-identity fingerprints."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import face_identity as fi  # noqa: E402


def _portrait(path: Path, *, face_color=(200, 160, 140), mark: bool = True) -> None:
    img = Image.new("RGB", (720, 1280), (30, 30, 40))
    draw = ImageDraw.Draw(img)
    # face oval upper center
    draw.ellipse((220, 160, 500, 520), fill=face_color)
    if mark:
        draw.ellipse((400, 340, 420, 360), fill=(40, 40, 40))  # beauty mark
    draw.ellipse((280, 280, 320, 320), fill=(40, 40, 60))  # eye
    draw.ellipse((400, 280, 440, 320), fill=(40, 40, 60))
    img.save(path)


def test_same_image_matches(tmp_path: Path):
    p = tmp_path / "a.png"
    _portrait(p)
    fp1 = fi.compute_fingerprint(p)
    fp2 = fi.compute_fingerprint(p)
    cmp_ = fi.compare_fingerprints(fp1, fp2)
    assert cmp_["ok"] is True
    assert cmp_["ahash_distance"] == 0
    assert cmp_["score"] == 0.0


def test_different_face_fails(tmp_path: Path):
    a = tmp_path / "cast.png"
    b = tmp_path / "other.png"
    _portrait(a, face_color=(200, 160, 140), mark=True)
    # very different: blue block face no features
    img = Image.new("RGB", (720, 1280), (10, 10, 80))
    draw = ImageDraw.Draw(img)
    draw.rectangle((100, 100, 620, 700), fill=(20, 40, 180))
    img.save(b)
    cmp_ = fi.compare_fingerprints(fi.compute_fingerprint(a), fi.compute_fingerprint(b))
    assert cmp_["ok"] is False


def test_enroll_and_verify(tmp_path: Path):
    root = tmp_path / "film"
    (root / "receipts").mkdir(parents=True)
    (root / "canonical" / "cast").mkdir(parents=True)
    cast = root / "canonical" / "cast" / "hero-master.png"
    still = root / "keyframes"
    still.mkdir()
    good = still / "shot01.png"
    _portrait(cast)
    _portrait(good)
    r = fi.enroll(root, "hero", cast)
    assert r["ok"]
    v = fi.verify_image(root, good, "hero")
    assert v["ok"] is True
    receipt = fi.load_receipt(root)
    assert "hero" in receipt["enrolled"]


def test_audit_sets_verified(tmp_path: Path):
    root = tmp_path / "film"
    (root / "receipts").mkdir(parents=True)
    cast_dir = root / "canonical" / "cast"
    cast_dir.mkdir(parents=True)
    kf = root / "keyframes"
    kf.mkdir()
    cast = cast_dir / "hero.png"
    _portrait(cast)
    _portrait(kf / "ep01_sc01_bt01_sh01.png")
    (root / "style-bible.json").write_text(
        '{"cast_masters": {"hero": "canonical/cast/hero.png"}}', encoding="utf-8"
    )
    out = fi.audit_keyframes(root, char_id="hero")
    assert out["verified"] is True
    assert out["n_fail"] == 0
    st = fi.post_audit_face_status(root)
    assert st["verified"] is True
    assert st["warnings"] == []
