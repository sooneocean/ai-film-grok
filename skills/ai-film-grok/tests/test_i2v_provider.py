#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from i2v_provider import (  # noqa: E402
    GrokI2VProvider,
    I2VProviderError,
    SeedanceProvider,
    all_providers,
    for_endpoint,
    get,
    registry_report,
    is_technical_failure,
    route_after_failure,
)


class I2VProviderTests(unittest.TestCase):
    def test_registry_has_grok_and_seedance(self) -> None:
        """DoD: both providers registered by default."""
        names = all_providers()
        self.assertIn("grok", names)
        self.assertIn("seedance", names)

    def test_grok_probe_ok(self) -> None:
        """The in-session probe is available without a film root."""
        report = get("grok").probe()
        self.assertTrue(report.ok)
        self.assertTrue(report.available)
        self.assertEqual(report.profile, "grok_primary")

    def test_grok_film_root_requires_live_canary(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            report = get("grok").probe(root=Path(raw))
            self.assertFalse(report.available)
            self.assertIn("canary", str(report.reason).lower())

    def test_grok_film_root_accepts_hash_bound_canary(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp_path = Path(raw)
            receipt = tmp_path / "receipts" / "grok-i2v-canary.json"
            receipt.parent.mkdir()
            receipt.write_text('{"ok": true, "output_sha256": "abc"}', encoding="utf-8")
            report = get("grok").probe(root=tmp_path)
            self.assertTrue(report.available)

    def test_endpoint_resolution(self) -> None:
        """Existing source_endpoint labels resolve to owning provider."""
        self.assertIsInstance(for_endpoint("image_to_video"), GrokI2VProvider)
        self.assertIsInstance(for_endpoint("frw_seedance_i2v"), SeedanceProvider)
        self.assertIsInstance(for_endpoint("frw_seedance_flf"), SeedanceProvider)
        # unknown endpoint → None
        self.assertIsNone(for_endpoint("nonexistent"))

    def test_seedance_models(self) -> None:
        sp = get("seedance")
        self.assertIn("seedance-2-fast-i2v", sp.MODELS.values())
        self.assertIn("seedance-2-pro-flf", sp.MODELS.values())
        self.assertIn("seedance-2-pro-lipsync", sp.MODELS.values())

    def test_seedance_build_command(self) -> None:
        """build_command returns a frw_dispatch newvideo invocation."""
        sp = get("seedance")
        cmd = sp.build_command(
            keyframe=Path("/tmp/kf.png"),
            prompt="@Image1 dolly-in",
            duration_sec=5,
            variant="i2v",
        )
        self.assertIn("newvideo", cmd)
        self.assertIn("seedance-2-fast-i2v", cmd)
        self.assertIn("--wait", cmd)

    def test_seedance_flf_variant(self) -> None:
        sp = get("seedance")
        cmd = sp.build_command(
            keyframe=Path("/tmp/kf.png"),
            prompt="@Image1 @Image2 union",
            variant="flf",
            img2_url="/tmp/kf2.png",
        )
        self.assertIn("seedance-2-pro-flf", cmd)
        self.assertIn("--img2-url", cmd)

    def test_grok_build_command(self) -> None:
        gp = get("grok")
        cmd = gp.build_command(
            keyframe=Path("/tmp/kf.png"),
            prompt="dolly-in",
            duration_sec=6,
            out="/tmp/clip.mp4",
        )
        self.assertTrue(cmd[1].endswith("grok_oauth_video.py"))
        self.assertIn("--out", cmd)
        self.assertNotIn("--wait", cmd)

    def test_unknown_provider_raises(self) -> None:
        with self.assertRaises(I2VProviderError):
            get("nonexistent")

    def test_registry_report(self) -> None:
        """registry_report lists all providers + active one."""
        report = registry_report()
        self.assertEqual(report["kind"], "i2v-provider-registry")
        names = [p["name"] for p in report["providers"]]
        self.assertIn("grok", names)
        self.assertIn("seedance", names)
        # active must be a registered provider
        self.assertIn(report["active"], report["registered"])

    def test_legacy_seedance_profile_cannot_change_preferred_provider(self) -> None:
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "seedance_first"}):
            self.assertIsInstance(__import__("i2v_provider").preferred(), GrokI2VProvider)

    def test_only_technical_failure_routes_to_frw(self) -> None:
        self.assertTrue(is_technical_failure("HTTP 503 service unavailable"))
        self.assertFalse(is_technical_failure({"task_id": "ambiguous"}))
        self.assertIsNone(route_after_failure(root=None, shot_id="s1", primary="grok", error="quality fail"))
        selected = route_after_failure(root=None, shot_id="s1", primary="grok", error="HTTP 503")
        self.assertIsNotNone(selected)
        self.assertEqual(selected[0].name, "seedance")

    def test_preferred_returns_registered(self) -> None:
        """preferred() never raises and returns a registered provider."""
        from i2v_provider import preferred

        provider = preferred()
        self.assertIn(provider.name, all_providers())


if __name__ == "__main__":
    unittest.main()
