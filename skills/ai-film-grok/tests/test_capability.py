#!/usr/bin/env python3
"""Tests for capability_report suggest/apply (no live FRW / Voicebox)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from capability_report import (  # noqa: E402
    apply_i2v_patch,
    build_capability_report,
    suggest_i2v_from_canary,
    summarize_frw_receipt,
)


@pytest.mark.slow
class SuggestI2VTests(unittest.TestCase):
    @pytest.mark.slow
    def test_seedance_201_suggests_frw(self) -> None:
        receipt = {
            "ok": True,
            "seedance_i2v": "201_submitted:abc",
            "ltx_t2v": "201_submitted:def",
            "recommended_l1": "seedance-2-fast-i2v",
            "recommended_l2": "ltx-t2v",
            "notes": "ok",
        }
        with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "grok_primary"}):
            s = suggest_i2v_from_canary(receipt, current_spec={})
        self.assertEqual(s["patch"].get("i2v_provider"), "frw")
        self.assertEqual(s["patch"].get("frw_video_model"), "seedance-2-fast-i2v")
        self.assertEqual(s["patch"].get("frw_env_model"), "ltx-t2v")
        self.assertTrue(s["rationale"])

    @pytest.mark.slow
    def test_seedance_403_suggests_grok(self) -> None:
        receipt = {
            "ok": True,
            "seedance_i2v": "403:forbidden",
            "ltx_t2v": "completed",
            "recommended_l1": "grok",
            "recommended_l2": "ltx-t2v",
            "notes": "seedance_403_permission,l1_prefer_grok_720p",
        }
        with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "grok_primary"}):
            s = suggest_i2v_from_canary(
                receipt,
                current_spec={
                    "i2v_provider": "frw",
                    "frw_video_model": "seedance-2-fast-i2v",
                },
            )
        self.assertEqual(s["patch"].get("i2v_provider"), "grok")
        self.assertEqual(s["patch"].get("frw_env_model"), "ltx-t2v")
        self.assertIn("i2v_provider", s["changes"])
        self.assertTrue(
            any("Grok" in r or "grok" in r for r in (s["recommendations"] + s["rationale"]))
        )

    @pytest.mark.slow
    def test_no_receipt(self) -> None:
        # Default action policy stays LTX-first even while its canary is absent.
        s = suggest_i2v_from_canary(None)
        self.assertFalse(s["has_canary"])
        self.assertFalse(s["ok"])
        self.assertEqual(s["patch"].get("i2v_provider"), "frw-ltx23")
        self.assertEqual(s["patch"].get("frw_env_model"), "ltx-t2v")
        self.assertTrue(s["recommendations"])

    @pytest.mark.slow
    def test_summarize(self) -> None:
        sm = summarize_frw_receipt(
            {"ok": True, "seedance_i2v": "403", "recommended_l1": "grok", "probed_at": "t"}
        )
        assert sm is not None
        self.assertTrue(sm["present"])
        self.assertEqual(sm["recommended_l1"], "grok")


@pytest.mark.slow
class ApplyPatchTests(unittest.TestCase):
    @pytest.mark.slow
    def test_apply_only_i2v_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = {
                "title": "t",
                "i2v_provider": "frw",
                "frw_video_model": "seedance-2-fast-i2v",
                "frw_env_model": "ltx-t2v",
                "tts_backend": "edge",
                "extra_should_stay": 1,
            }
            (root / "film-spec.json").write_text(
                json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            patch = {
                "i2v_provider": "grok",
                "frw_env_model": "ltx-t2v",
                "hack_me": "nope",
            }
            result = apply_i2v_patch(root, patch, dry_run=False)
            self.assertTrue(result["ok"])
            self.assertIn("i2v_provider", result["applied"])
            self.assertNotIn("hack_me", result["applied"])
            loaded = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            self.assertEqual(loaded["i2v_provider"], "grok")
            self.assertEqual(loaded["tts_backend"], "edge")
            self.assertEqual(loaded["extra_should_stay"], 1)
            self.assertIn("_capability_apply", loaded)

    @pytest.mark.slow
    def test_apply_dry_run_no_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "film-spec.json").write_text(
                json.dumps({"i2v_provider": "frw"}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            apply_i2v_patch(root, {"i2v_provider": "grok"}, dry_run=True)
            loaded = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            self.assertEqual(loaded["i2v_provider"], "frw")


@pytest.mark.slow
class BuildReportSmoke(unittest.TestCase):
    @pytest.mark.slow
    def test_global_report_shape(self) -> None:
        report = build_capability_report(root=None)
        self.assertIn("tts", report)
        self.assertIn("tools", report)
        self.assertIn("recommendations", report)
        self.assertIn("usage", report)
        self.assertIsNone(report.get("root"))
        self.assertIn("edge", report["tts"])
        self.assertIn("voicebox", report["tts"])
        self.assertIn("fallback_enabled", report["tts"])

    @pytest.mark.slow
    def test_root_with_fake_canary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "receipts").mkdir()
            canary = {
                "ok": True,
                "seedance_i2v": "403:no",
                "ltx_t2v": "completed",
                "recommended_l1": "grok",
                "recommended_l2": "ltx-t2v",
                "notes": "seedance_403_permission,l1_prefer_grok_720p",
                "probed_at": "2026-07-21T00:00:00+00:00",
            }
            (root / "receipts" / "frw-key-capability.json").write_text(
                json.dumps(canary) + "\n", encoding="utf-8"
            )
            (root / "film-spec.json").write_text(
                json.dumps(
                    {
                        "i2v_provider": "frw",
                        "frw_video_model": "seedance-2-fast-i2v",
                        "frw_env_model": "ltx-t2v",
                        "tts_backend": "edge",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            report = build_capability_report(root=root, suggest_i2v=True)
            self.assertTrue(report["frw"]["present"])
            self.assertEqual(report["suggested_film_spec_patch"]["i2v_provider"], "frw-ltx23")
            # no silent apply
            loaded = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            self.assertEqual(loaded["i2v_provider"], "frw")

            report2 = build_capability_report(root=root, suggest_i2v=True, apply=True)
            self.assertTrue(report2["apply"]["ok"])
            loaded2 = json.loads((root / "film-spec.json").read_text(encoding="utf-8"))
            self.assertEqual(loaded2["i2v_provider"], "frw-ltx23")


if __name__ == "__main__":
    unittest.main()
