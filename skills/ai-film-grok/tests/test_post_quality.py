"""Tests for post_quality.py — VFX registry, audio delivery, and premium master QC.

Previously had ZERO test coverage. Tests cover:
  - register_vfx_shot: status validation, hash binding, receipt writing
  - vfx_gate: stale hash detection, missing registry, unapproved shots
  - audio_delivery_gate: stems/audio contract
  - premium_master_qc: vertical video gate (requires ffmpeg for ffprobe)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from post_quality import (  # noqa: E402
    audio_delivery_gate,
    premium_master_qc,
    register_vfx_shot,
    vfx_gate,
)


class TestRegisterVfxShot(unittest.TestCase):
    """register_vfx_shot registers a VFX plate with hash binding."""

    def test_register_valid_shot(self):
        """Valid registration → shot in registry with hash."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plate = root / "plate.png"
            plate.write_bytes(b"plate data")

            report = register_vfx_shot(
                root,
                shot_id="shot01",
                plate=str(plate),
                status="approved",
                reviewer="dex",
            )
            self.assertIn("shot01", report["shots"])
            self.assertEqual(report["shots"]["shot01"]["status"], "approved")
            self.assertIsNotNone(report["shots"]["shot01"]["plate_sha256"])
            self.assertTrue(report["ok"])  # all approved → ok
            self.assertTrue((root / "receipts" / "vfx-shots.json").is_file())

    def test_rejects_invalid_status(self):
        """Invalid status raises ValueError."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plate = root / "plate.png"
            plate.write_bytes(b"data")
            with self.assertRaises(ValueError):
                register_vfx_shot(
                    root,
                    shot_id="shot01",
                    plate=str(plate),
                    status="invalid",
                    reviewer="dex",
                )

    def test_rejects_empty_shot_id(self):
        """Empty shot_id raises ValueError."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plate = root / "plate.png"
            plate.write_bytes(b"data")
            with self.assertRaises(ValueError):
                register_vfx_shot(
                    root,
                    shot_id="  ",
                    plate=str(plate),
                    status="approved",
                    reviewer="dex",
                )

    def test_unapproved_shot_makes_report_not_ok(self):
        """Pending status → report ok=False."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plate = root / "plate.png"
            plate.write_bytes(b"data")
            report = register_vfx_shot(
                root,
                shot_id="shot01",
                plate=str(plate),
                status="pending",
                reviewer="dex",
            )
            self.assertFalse(report["ok"])

    def test_multiple_shots_accumulate(self):
        """Multiple registrations accumulate in same registry."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plate1 = root / "p1.png"
            plate1.write_bytes(b"a")
            plate2 = root / "p2.png"
            plate2.write_bytes(b"b")

            register_vfx_shot(
                root,
                shot_id="shot01",
                plate=str(plate1),
                status="approved",
                reviewer="dex",
            )
            register_vfx_shot(
                root,
                shot_id="shot02",
                plate=str(plate2),
                status="approved",
                reviewer="dex",
            )
            report = register_vfx_shot(
                root,
                shot_id="shot03",
                plate=str(plate1),
                status="review",
                reviewer="dex",
            )
            self.assertEqual(len(report["shots"]), 3)
            self.assertFalse(report["ok"])  # shot03 not approved


class TestVfxGate(unittest.TestCase):
    """vfx_gate checks VFX registry completeness."""

    def test_missing_registry(self):
        """No vfx-shots.json → VFX_REGISTRY_MISSING blocker."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = vfx_gate(root)
            self.assertFalse(report["ok"])
            codes = {b["code"] for b in report["blockers"]}
            self.assertIn("VFX_REGISTRY_MISSING", codes)

    def test_unapproved_shot_blocks(self):
        """Pending shot → VFX_NOT_APPROVED blocker."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plate = root / "plate.png"
            plate.write_bytes(b"data")
            register_vfx_shot(
                root,
                shot_id="shot01",
                plate=str(plate),
                status="pending",
                reviewer="dex",
            )
            report = vfx_gate(root)
            self.assertFalse(report["ok"])
            codes = {b["code"] for b in report["blockers"]}
            self.assertIn("VFX_NOT_APPROVED", codes)

    def test_stale_plate_hash_blocks(self):
        """Modified plate after registration → VFX_PLATE_STALE blocker."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plate = root / "plate.png"
            plate.write_bytes(b"original")
            register_vfx_shot(
                root,
                shot_id="shot01",
                plate=str(plate),
                status="approved",
                reviewer="dex",
            )
            # Modify plate
            plate.write_bytes(b"modified")
            report = vfx_gate(root)
            self.assertFalse(report["ok"])
            codes = {b["code"] for b in report["blockers"]}
            self.assertIn("VFX_PLATE_STALE", codes)

    def test_all_approved_passes(self):
        """All shots approved with matching hashes → ok=True."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plate = root / "plate.png"
            plate.write_bytes(b"data")
            register_vfx_shot(
                root,
                shot_id="shot01",
                plate=str(plate),
                status="approved",
                reviewer="dex",
            )
            report = vfx_gate(root)
            self.assertTrue(report["ok"])


class TestAudioDeliveryGate(unittest.TestCase):
    """audio_delivery_gate checks audio stems contract."""

    def test_missing_audio_dir(self):
        """No audio/stems → blockers."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = audio_delivery_gate(root)
            self.assertFalse(report["ok"])


class TestPremiumMasterQc(unittest.TestCase):
    """premium_master_qc checks vertical video + all post gates."""

    def test_empty_root_fails(self):
        """Empty root → blockers, ok=False."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = premium_master_qc(root)
            self.assertFalse(report["ok"])


if __name__ == "__main__":
    unittest.main()
