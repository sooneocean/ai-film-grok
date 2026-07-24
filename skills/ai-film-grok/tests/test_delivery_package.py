"""Tests for delivery_package.py — premium vertical delivery package contract.

Previously had ZERO test coverage. Tests cover:
  - build_delivery_package: missing assets → blockers, allow_missing mode
  - hash binding (sha256 of assets)
  - stems directory detection
  - provenance.json passthrough
  - receipt writing
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from delivery_package import REQUIRED, build_delivery_package  # noqa: E402


class TestBuildDeliveryPackage(unittest.TestCase):
    """build_delivery_package validates premium delivery assets."""

    def test_empty_root_all_missing(self):
        """No assets → all blockers, ok=False."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir(parents=True)
            (root / "receipts").mkdir(parents=True)
            report = build_delivery_package(root)
            self.assertFalse(report["ok"])
            codes = {b["code"] for b in report["blockers"]}
            self.assertIn("DELIVERY_ASSET_MISSING", codes)
            self.assertIn("STEMS_MISSING", codes)
            # All asset roles present with null paths
            for role in REQUIRED:
                self.assertIn(role, report["assets"])
                self.assertIsNone(report["assets"][role]["path"])

    def test_allow_missing_mode(self):
        """allow_missing=True → no blockers even with missing assets."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir(parents=True)
            (root / "receipts").mkdir(parents=True)
            report = build_delivery_package(root, allow_missing=True)
            self.assertTrue(report["ok"])
            self.assertEqual(report["blockers"], [])

    def test_with_assets_and_stems(self):
        """All required assets present + stems → ok=True."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            out.mkdir(parents=True)
            (root / "receipts").mkdir(parents=True)
            # Create required assets
            (out / "film_final.mp4").write_bytes(b"video")
            (out / "final.srt").write_text("1\n00:00:01,000 --> 00:00:03,000\nhi\n")
            (out / "edit.edl").write_text("EDL content")
            (out / "film_final_clean.mp4").write_bytes(b"clean")
            # Mezzanine (prores)
            (out / "film_final_prores.mov").write_bytes(b"prores")
            # Stems
            stems = root / "audio" / "stems"
            stems.mkdir(parents=True)
            (stems / "dialogue.wav").write_bytes(b"dialog")
            (stems / "music.wav").write_bytes(b"music")

            report = build_delivery_package(root)
            self.assertTrue(report["ok"])
            self.assertEqual(report["blockers"], [])
            # Check assets have hashes
            self.assertIsNotNone(report["assets"]["publish"]["sha256"])
            self.assertIsNotNone(report["assets"]["subtitle"]["sha256"])
            # Stems detected
            self.assertEqual(len(report["stems"]), 2)
            # Receipt written
            receipt = root / "receipts" / "premium-delivery-package.json"
            self.assertTrue(receipt.is_file())

    def test_candidate_fallback(self):
        """Second candidate name works when first is missing."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            out.mkdir(parents=True)
            (root / "receipts").mkdir(parents=True)
            # publish has candidates: film_final.mp4, film_final_h264.mp4, film_final_h265.mp4
            (out / "film_final_h265.mp4").write_bytes(b"h265")
            # Other required assets + stems
            (out / "final.srt").write_text("srt")
            (out / "edit.edl").write_text("edl")
            (out / "film_final_clean.mp4").write_bytes(b"c")
            (out / "film_final_prores.mov").write_bytes(b"p")
            stems = root / "audio" / "stems"
            stems.mkdir(parents=True)
            (stems / "s.wav").write_bytes(b"s")

            report = build_delivery_package(root)
            self.assertTrue(report["ok"])
            self.assertIn("h265", report["assets"]["publish"]["path"])

    def test_provenance_passthrough(self):
        """provenance.json is read and included in report."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir(parents=True)
            (root / "receipts").mkdir(parents=True)
            prov = {"version": "1.0", "tool": "aifilm"}
            (root / "provenance.json").write_text(json.dumps(prov))

            report = build_delivery_package(root, allow_missing=True)
            self.assertEqual(report["provenance"], prov)

    def test_stale_hash_detected(self):
        """Hash changes when asset content changes → old receipt hash is stale."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "out"
            out.mkdir(parents=True)
            (root / "receipts").mkdir(parents=True)
            (out / "film_final.mp4").write_bytes(b"original")
            (out / "final.srt").write_text("s")
            (out / "edit.edl").write_text("e")
            (out / "film_final_clean.mp4").write_bytes(b"c")
            (out / "film_final_prores.mov").write_bytes(b"p")
            stems = root / "audio" / "stems"
            stems.mkdir(parents=True)
            (stems / "s.wav").write_bytes(b"s")

            report1 = build_delivery_package(root)
            hash1 = report1["assets"]["publish"]["sha256"]

            # Modify the asset
            (out / "film_final.mp4").write_bytes(b"modified")
            report2 = build_delivery_package(root)
            hash2 = report2["assets"]["publish"]["sha256"]

            self.assertNotEqual(hash1, hash2)


if __name__ == "__main__":
    unittest.main()
