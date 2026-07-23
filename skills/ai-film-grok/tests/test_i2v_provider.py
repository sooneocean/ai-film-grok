#!/usr/bin/env python3
from __future__ import annotations

import sys
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
)


class I2VProviderTests(unittest.TestCase):
    def test_registry_has_grok_and_seedance(self) -> None:
        """DoD: both providers registered by default."""
        names = all_providers()
        self.assertIn("grok", names)
        self.assertIn("seedance", names)

    def test_grok_probe_ok(self) -> None:
        """Grok is the always-available fallback."""
        report = get("grok").probe()
        self.assertTrue(report.ok)
        self.assertTrue(report.available)
        self.assertEqual(report.profile, "grok_primary")

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
        cmd = gp.build_command(keyframe=Path("/tmp/kf.png"), prompt="dolly-in", duration_sec=6)
        self.assertIn("video", cmd)
        self.assertIn("--wait", cmd)

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

    def test_preferred_returns_registered(self) -> None:
        """preferred() never raises and returns a registered provider."""
        from i2v_provider import preferred

        provider = preferred()
        self.assertIn(provider.name, all_providers())


if __name__ == "__main__":
    unittest.main()
