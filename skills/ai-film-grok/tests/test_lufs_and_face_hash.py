"""Tests for LUFS hard gate + perceptual hash face identity.

P3-4: LUFS_OUT_OF_RANGE — warning by default, hard when lufs_strict=true.
P2-1 extend: face_identity_hash — perceptual hash verification.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from post_audit import audit


def _make_film_root(tmp_path: Path, *, spec=None, mix_report=None):
    if spec:
        (tmp_path / "film-spec.json").write_text(json.dumps(spec, ensure_ascii=False))
    if mix_report:
        adir = tmp_path / "audio"
        adir.mkdir(exist_ok=True)
        (adir / "mix_report.json").write_text(json.dumps(mix_report, ensure_ascii=False))
    outdir = tmp_path / "out"
    outdir.mkdir(exist_ok=True)
    (outdir / "film_final.mp4").write_bytes(b"fake mp4")


class TestLufsGate:
    """LUFS_OUT_OF_RANGE in post_audit."""

    def test_lufs_warning_when_out_of_range(self, tmp_path):
        spec = {"title": "t", "vo_mode": "s", "scenes": []}
        mix = {"loudness": {"integrated": -30.0}}  # too quiet
        _make_film_root(tmp_path, spec=spec, mix_report=mix)
        result = audit(tmp_path, write=False)
        codes = [w["code"] for w in result.get("warnings", [])]
        assert "LUFS_OUT_OF_RANGE" in codes

    def test_lufs_hard_when_strict(self, tmp_path):
        spec = {"title": "t", "vo_mode": "s", "scenes": [], "lufs_strict": True}
        mix = {"loudness": {"integrated": -5.0}}  # way too loud
        _make_film_root(tmp_path, spec=spec, mix_report=mix)
        result = audit(tmp_path, write=False)
        hard_codes = [h["code"] for h in result.get("hard_failures", [])]
        assert "LUFS_OUT_OF_RANGE" in hard_codes

    def test_lufs_in_range_no_issue(self, tmp_path):
        spec = {"title": "t", "vo_mode": "s", "scenes": []}
        mix = {"loudness": {"integrated": -16.0}}  # within range
        _make_film_root(tmp_path, spec=spec, mix_report=mix)
        result = audit(tmp_path, write=False)
        codes = [w["code"] for w in result.get("warnings", [])]
        assert "LUFS_OUT_OF_RANGE" not in codes

    def test_custom_lufs_range(self, tmp_path):
        spec = {
            "title": "t",
            "vo_mode": "s",
            "scenes": [],
            "lufs_strict": True,
            "lufs_min": -20,
            "lufs_max": -15,
        }
        mix = {"loudness": {"integrated": -22.0}}  # below custom min
        _make_film_root(tmp_path, spec=spec, mix_report=mix)
        result = audit(tmp_path, write=False)
        hard_codes = [h["code"] for h in result.get("hard_failures", [])]
        assert "LUFS_OUT_OF_RANGE" in hard_codes


class TestFaceIdentityHash:
    """Perceptual hash face identity verification."""

    def test_identical_images_verified(self, tmp_path):
        from PIL import Image

        # Create two identical images
        img = Image.new("RGB", (64, 64), color=(128, 100, 80))
        img1_path = tmp_path / "cast.png"
        img2_path = tmp_path / "still.png"
        img.save(img1_path)
        img.save(img2_path)

        from face_identity_hash import verify_face_identity

        result = verify_face_identity(img1_path, img2_path)
        assert result["verified"] is True
        assert result["distance"] == 0

    def test_different_images_not_verified(self, tmp_path):
        from PIL import Image, ImageDraw

        # Create two very different images with patterns
        img1 = Image.new("RGB", (64, 64), color=(255, 255, 255))
        draw1 = ImageDraw.Draw(img1)
        draw1.rectangle([10, 10, 50, 50], fill=(0, 0, 0))

        img2 = Image.new("RGB", (64, 64), color=(0, 0, 0))
        draw2 = ImageDraw.Draw(img2)
        draw2.ellipse([5, 5, 55, 55], fill=(255, 255, 255))

        img1_path = tmp_path / "cast.png"
        img2_path = tmp_path / "still.png"
        img1.save(img1_path)
        img2.save(img2_path)

        from face_identity_hash import verify_face_identity

        result = verify_face_identity(img1_path, img2_path, max_distance=5)
        assert result["verified"] is False
        assert result["distance"] > 5

    def test_missing_cast_master(self, tmp_path):
        from face_identity_hash import verify_face_identity

        result = verify_face_identity(tmp_path / "nonexistent.png", tmp_path / "also.png")
        assert result["verified"] is False
        assert "not found" in result.get("error", "")

    def test_receipt_written(self, tmp_path):
        from PIL import Image

        img = Image.new("RGB", (64, 64), color=(128, 100, 80))
        img1_path = tmp_path / "cast.png"
        img2_path = tmp_path / "still.png"
        img.save(img1_path)
        img.save(img2_path)

        from face_identity_hash import write_identity_receipt

        receipt = write_identity_receipt(tmp_path, img1_path, [img2_path])
        assert receipt["verified"] is True
        assert (tmp_path / "receipts" / "face-identity.json").is_file()

        # Verify receipt is readable by post_audit
        saved = json.loads((tmp_path / "receipts" / "face-identity.json").read_text())
        assert saved["verified"] is True
        assert saved["method"] == "perceptual_hash_ahash"
