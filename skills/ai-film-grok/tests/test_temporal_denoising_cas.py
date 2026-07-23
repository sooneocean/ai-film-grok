"""Unit tests for Plate 12: Temporal Edge-Aware Denoising & CAS Sharpening Engine.

Verifies:
1. render_final.py build_post_enhancement_vf_chain video filter chain construction.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from render_final import build_post_enhancement_vf_chain  # noqa: E402


class TemporalDenoisingCASTests(unittest.TestCase):
    def test_build_post_enhancement_vf_chain_both(self) -> None:
        chain = build_post_enhancement_vf_chain(enable_denoise=True, enable_sharpen=True)
        self.assertIn("hqdn3d=2.0:1.5:3.0:2.5", chain)
        self.assertIn("cas=strength=0.35", chain)

    def test_build_post_enhancement_vf_chain_denoise_only(self) -> None:
        chain = build_post_enhancement_vf_chain(enable_denoise=True, enable_sharpen=False)
        self.assertIn("hqdn3d", chain)
        self.assertNotIn("cas", chain)

    def test_build_post_enhancement_vf_chain_sharpen_only(self) -> None:
        chain = build_post_enhancement_vf_chain(enable_denoise=False, enable_sharpen=True)
        self.assertNotIn("hqdn3d", chain)
        self.assertIn("cas", chain)


if __name__ == "__main__":
    unittest.main()
