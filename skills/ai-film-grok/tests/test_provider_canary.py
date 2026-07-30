"""Tests for provider_canary.py — truthful provider canary receipts.

Previously had ZERO test coverage. Tests cover:
  - record_canary: provider validation, hash binding, receipt writing
  - canary_status: stale detection, missing file, hash mismatch
  - provider-specific receipt paths (grok vs seedance)
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from provider_canary import canary_status, record_canary  # noqa: E402


class TestRecordCanary(unittest.TestCase):
    """record_canary writes hash-bound provider canary receipts."""

    def test_successful_grok_canary(self):
        """Valid grok canary with identity+motion ok → ok=True."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir(parents=True)
            media = root / "out" / "canary.mp4"
            media.parent.mkdir(parents=True)
            media.write_bytes(b"canary video")

            report = record_canary(
                root,
                provider="grok",
                output=str(media),
                reviewer="dex",
                identity_ok=True,
                motion_ok=True,
            )
            self.assertTrue(report["ok"])
            self.assertEqual(report["provider"], "grok")
            self.assertIsNotNone(report["output_sha256"])
            # Main receipt + provider-specific receipt
            self.assertTrue((root / "receipts" / "provider-canary.json").is_file())
            self.assertTrue((root / "receipts" / "grok-i2v-canary.json").is_file())

    def test_seedance_canary_writes_different_receipt(self):
        """Seedance canary writes seedance-canary.json, not grok-i2v-canary.json."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir(parents=True)
            media = root / "out" / "canary.mp4"
            media.parent.mkdir(parents=True)
            media.write_bytes(b"seedance")

            record_canary(
                root,
                provider="seedance",
                output=str(media),
                reviewer="dex",
                identity_ok=True,
                motion_ok=True,
            )
            self.assertTrue((root / "receipts" / "seedance-canary.json").is_file())
            self.assertFalse((root / "receipts" / "grok-i2v-canary.json").is_file())

    def test_rejects_invalid_provider(self):
        """Invalid provider raises ValueError."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "out" / "canary.mp4"
            media.parent.mkdir(parents=True)
            media.write_bytes(b"data")

            with self.assertRaises(ValueError) as ctx:
                record_canary(
                    root,
                    provider="openai",
                    output=str(media),
                    reviewer="dex",
                    identity_ok=True,
                    motion_ok=True,
                )
            self.assertIn("provider", str(ctx.exception))

    def test_rejects_missing_media(self):
        """Non-existent media file raises ValueError."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError) as ctx:
                record_canary(
                    root,
                    provider="grok",
                    output=str(root / "nonexistent.mp4"),
                    reviewer="dex",
                    identity_ok=True,
                    motion_ok=True,
                )
            self.assertIn("must be a real", str(ctx.exception))

    def test_identity_motion_failure(self):
        """identity_ok=False or motion_ok=False → ok=False."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir(parents=True)
            media = root / "canary.mp4"
            media.write_bytes(b"data")

            report = record_canary(
                root,
                provider="grok",
                output=str(media),
                reviewer="dex",
                identity_ok=False,
                motion_ok=True,
            )
            self.assertFalse(report["ok"])

    def test_relative_output_resolved(self):
        """Relative output path is resolved against root."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir(parents=True)
            (root / "out").mkdir(parents=True)
            (root / "out" / "relative.mp4").write_bytes(b"rel")

            report = record_canary(
                root,
                provider="grok",
                output="out/relative.mp4",
                reviewer="dex",
                identity_ok=True,
                motion_ok=True,
            )
            self.assertTrue(report["ok"])
            self.assertTrue(report["output"].endswith("relative.mp4"))


class TestCanaryStatus(unittest.TestCase):
    """canary_status checks freshness of canary receipt."""

    def test_fresh_canary_ok(self):
        """Canary with matching hash → ok=True, stale=False."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir(parents=True)
            media = root / "canary.mp4"
            media.write_bytes(b"data")

            record_canary(
                root,
                provider="grok",
                output=str(media),
                reviewer="dex",
                identity_ok=True,
                motion_ok=True,
            )
            status = canary_status(root)
            self.assertTrue(status["ok"])
            self.assertFalse(status["stale"])

    def test_stale_canary_detected(self):
        """Modified media after canary → stale=True, ok=False."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir(parents=True)
            media = root / "canary.mp4"
            media.write_bytes(b"original")

            record_canary(
                root,
                provider="grok",
                output=str(media),
                reviewer="dex",
                identity_ok=True,
                motion_ok=True,
            )
            # Modify media
            media.write_bytes(b"modified")
            status = canary_status(root)
            self.assertFalse(status["ok"])
            self.assertTrue(status["stale"])

    def test_missing_canary_receipt(self):
        """No canary receipt → empty status, ok=False."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            status = canary_status(root)
            self.assertFalse(status["ok"])
            self.assertFalse(status.get("stale", False))


if __name__ == "__main__":
    unittest.main()
