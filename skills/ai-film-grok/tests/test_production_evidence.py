#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from production_evidence import build_evidence  # noqa: E402


class ProductionEvidenceTests(unittest.TestCase):
    def test_empty_root_is_not_bulk_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = build_evidence(Path(tmp))
            self.assertTrue(report["ok"])
            self.assertFalse(report["ready_for_bulk"])
            self.assertEqual(report["evidence"]["motion"]["clip_count"], 0)
            self.assertTrue(report["next"])

    def test_receipt_presence_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            (root / "receipts" / "tts-rehearsal.json").write_text("{}\n", encoding="utf-8")
            (root / "audio").mkdir()
            (root / "audio" / "mix_report.json").write_text("{}\n", encoding="utf-8")
            report = build_evidence(root)
            self.assertTrue(report["evidence"]["audio"]["tts_rehearsal"])
            self.assertTrue(report["evidence"]["audio"]["mix_report"])


if __name__ == "__main__":
    unittest.main()
