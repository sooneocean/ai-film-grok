#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from post_audit import audit, audit_freshness  # noqa: E402


class PostAuditTests(unittest.TestCase):
    def test_empty_root_is_not_delivery_ready_and_writes_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = audit(root)
            self.assertFalse(report["delivery_ready"])
            self.assertTrue(any(x["code"] == "FINAL_MP4_MISSING" for x in report["hard_failures"]))
            self.assertTrue((root / "receipts" / "post-audit.json").is_file())
            self.assertTrue((root / "receipts" / "post-audit.md").is_file())

    def test_manifest_hash_mismatch_is_hard_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            (root / "out" / "final.mp4").write_bytes(b"not a real mp4")
            (root / "manifest.json").write_text(
                json.dumps(
                    {"outputs": {"final_film": {"path": "out/final.mp4", "sha256": "wrong"}}}
                ),
                encoding="utf-8",
            )
            report = audit(root, write=False)
            self.assertTrue(any(x["code"] == "FINAL_HASH_STALE" for x in report["hard_failures"]))

    def test_stored_receipt_becomes_stale_after_subtitle_change(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            subtitle = root / "out" / "final.srt"
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nold\n", encoding="utf-8")
            first = audit(root, write=False)
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nnew\n", encoding="utf-8")
            fresh = audit_freshness(root, first)
            self.assertTrue(fresh["stale"])
            self.assertIn("subtitles", fresh["mismatches"])

    def test_burned_subtitles_plus_compose_captions_is_hard_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            (root / "compose" / "remotion" / "public").mkdir(parents=True)
            (root / "compose" / "remotion" / "public" / "captions.json").write_text(
                "[]\n", encoding="utf-8"
            )
            (root / "out" / "final-delivery.json").write_text(
                '{"subtitles":{"burned_in":true}}\n', encoding="utf-8"
            )
            report = audit(root, write=False)
            self.assertTrue(
                any(x["code"] == "SUBTITLE_DOUBLE_BURN_RISK" for x in report["hard_failures"])
            )

    def test_delivery_sidecar_subtitle_hash_mismatch_is_hard_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            (root / "out" / "final.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n字幕\n", encoding="utf-8"
            )
            (root / "out" / "final-delivery.json").write_text(
                '{"subtitles":{"srt_sha256":"wrong"}}\n', encoding="utf-8"
            )
            report = audit(root, write=False)
            self.assertTrue(
                any(x["code"] == "SIDECAR_SUBTITLES_HASH_MISMATCH" for x in report["hard_failures"])
            )

    def test_delivery_v2_requires_complete_provenance_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            (root / "out" / "final.srt").write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n字幕\n", encoding="utf-8"
            )
            (root / "out" / "final-delivery.json").write_text(
                '{"schema_version":2,"output_sha256":"final"}\n', encoding="utf-8"
            )
            report = audit(root, write=False)
            self.assertTrue(
                any(
                    item["code"] == "DELIVERY_PROVENANCE_INCOMPLETE"
                    for item in report["hard_failures"]
                )
            )

    def test_delivery_v1_emits_migration_warning_not_provenance_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            (root / "out" / "final-delivery.json").write_text(
                '{"schema_version":1,"output_sha256":"final"}\n', encoding="utf-8"
            )
            report = audit(root, write=False)
            codes = {item["code"] for item in report["warnings"]}
            self.assertIn("DELIVERY_PROVENANCE_LEGACY", codes)

    def test_approved_review_requires_all_scorecard_and_screening_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "out").mkdir()
            (root / "out" / "final-review.json").write_text(
                '{"approved":true,"scorecard":{"audio":true}}\n', encoding="utf-8"
            )
            report = audit(root, write=False)
            codes = {item["code"] for item in report["hard_failures"]}
            self.assertIn("FINAL_SCORECARD_INCOMPLETE", codes)
            self.assertIn("SCREENING_EVIDENCE_INCOMPLETE", codes)


if __name__ == "__main__":
    unittest.main()
