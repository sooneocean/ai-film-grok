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


class PremiumGateElevationTests(unittest.TestCase):
    """P2-6/P2-8: premium projects elevate face-identity drift + color-grade to hard."""

    def test_premium_face_identity_drift_is_hard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "style-bible.json").write_text(
                json.dumps({"cast_masters": {"hero": "cast/hero-v1.png"}}), encoding="utf-8"
            )
            (root / "production-book.json").write_text(
                json.dumps({"quality_target": "premium_vertical"}), encoding="utf-8"
            )
            # No receipts/face-identity.json → drift
            report = audit(root, write=False)
            hard_codes = {item["code"] for item in report["hard_failures"]}
            self.assertIn("FACE_IDENTITY_DRIFT", hard_codes)

    def test_standard_face_identity_drift_is_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "style-bible.json").write_text(
                json.dumps({"cast_masters": {"hero": "cast/hero-v1.png"}}), encoding="utf-8"
            )
            (root / "production-book.json").write_text(
                json.dumps({"quality_target": "standard"}), encoding="utf-8"
            )
            report = audit(root, write=False)
            hard_codes = {item["code"] for item in report["hard_failures"]}
            warn_codes = {item["code"] for item in report["warnings"]}
            self.assertNotIn("FACE_IDENTITY_DRIFT", hard_codes)
            self.assertIn("FACE_IDENTITY_DRIFT", warn_codes)

    def test_premium_color_grade_missing_is_hard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(json.dumps({"title": "t"}), encoding="utf-8")
            (root / "production-book.json").write_text(
                json.dumps({"quality_target": "premium_vertical"}), encoding="utf-8"
            )
            report = audit(root, write=False)
            hard_codes = {item["code"] for item in report["hard_failures"]}
            self.assertIn("COLOR_GRADE_MISSING", hard_codes)

    def test_standard_color_grade_missing_is_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(json.dumps({"title": "t"}), encoding="utf-8")
            (root / "production-book.json").write_text(
                json.dumps({"quality_target": "standard"}), encoding="utf-8"
            )
            report = audit(root, write=False)
            hard_codes = {item["code"] for item in report["hard_failures"]}
            warn_codes = {item["code"] for item in report["warnings"]}
            self.assertNotIn("COLOR_GRADE_MISSING", hard_codes)
            self.assertIn("COLOR_GRADE_MISSING", warn_codes)

    def test_premium_audio_bible_violation_is_hard(self) -> None:
        """P2-11: premium projects elevate audio_bible advisory to hard at delivery."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "production-book.json").write_text(
                json.dumps({"quality_target": "premium_vertical"}), encoding="utf-8"
            )
            (root / "audio-bible.json").write_text(
                json.dumps({"schema_version": 1, "kind": "audio-bible", "nodes": {}}),
                encoding="utf-8",
            )
            report = audit(root, write=False)
            hard_codes = {item["code"] for item in report["hard_failures"]}
            self.assertIn("VOICE_LOCK_MISSING", hard_codes)

    def test_premium_post_bible_violation_is_hard(self) -> None:
        """P2-11: premium projects elevate post_bible advisory to hard at delivery."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "production-book.json").write_text(
                json.dumps({"quality_target": "premium_vertical"}), encoding="utf-8"
            )
            (root / "post-bible.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "post-bible",
                        "nodes": {
                            "mix": {"data": {"integrated_lufs": -10.0, "true_peak_dbtp": 0.5}},
                        },
                    }
                ),
                encoding="utf-8",
            )
            report = audit(root, write=False)
            hard_codes = {item["code"] for item in report["hard_failures"]}
            self.assertTrue(
                hard_codes & {"MIX_LUFS_OUT_OF_RANGE", "MIX_TRUE_PEAK_TOO_HIGH"},
                f"expected mix violation in hard, got {hard_codes}",
            )

    def test_standard_audio_bible_not_checked(self) -> None:
        """Standard projects don't check audio_bible at delivery (advisory only)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "production-book.json").write_text(
                json.dumps({"quality_target": "standard"}), encoding="utf-8"
            )
            (root / "audio-bible.json").write_text(
                json.dumps({"schema_version": 1, "kind": "audio-bible", "nodes": {}}),
                encoding="utf-8",
            )
            report = audit(root, write=False)
            hard_codes = {item["code"] for item in report["hard_failures"]}
            self.assertNotIn("VOICE_LOCK_MISSING", hard_codes)


class UnifiedLufsStandardTests(unittest.TestCase):
    """P3-15: LUFS standard unified to -16 ±2 (-18..-14) across all modules."""

    def test_post_bible_lufs_band_is_unified(self):
        """post_bible MIX_LUFS_OUT_OF_RANGE uses -18..-14 (was -24..-14)."""
        from post_bible import validate_post_bible

        # -16 is in range → no LUFS error
        bible = {
            "schema_version": 1,
            "kind": "post-bible",
            "nodes": {
                "mix": {
                    "data": {
                        "integrated_lufs": -16.0,
                        "true_peak_dbtp": -2.0,
                        "degraded_from": None,
                    }
                },
            },
        }
        rep = validate_post_bible(bible)
        codes = {e["code"] for e in rep.get("errors") or []}
        self.assertNotIn("MIX_LUFS_OUT_OF_RANGE", codes)

        # -22 is out of range → error (previously -24..-14 would have passed)
        bible["nodes"]["mix"]["data"]["integrated_lufs"] = -22.0
        rep = validate_post_bible(bible)
        codes = {e["code"] for e in rep.get("errors") or []}
        self.assertIn("MIX_LUFS_OUT_OF_RANGE", codes)

    def test_quality_check_video_lufs_band_is_unified(self):
        """quality_check_video MEAN_VOLUME constants are -18..-14 (was -22..-16)."""
        import quality_check_video

        self.assertAlmostEqual(quality_check_video.MEAN_VOLUME_MIN_DB, -18.0)
        self.assertAlmostEqual(quality_check_video.MEAN_VOLUME_MAX_DB, -14.0)

    def test_quality_check_video_strict_audio_loudness_param(self):
        """The strict_audio_loudness parameter exists on run_quality_check."""
        import inspect

        import quality_check_video

        sig = inspect.signature(quality_check_video.run_quality_check)
        self.assertIn("strict_audio_loudness", sig.parameters)
        self.assertFalse(sig.parameters["strict_audio_loudness"].default)


if __name__ == "__main__":
    unittest.main()
