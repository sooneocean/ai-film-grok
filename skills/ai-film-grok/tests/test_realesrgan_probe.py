"""Unit tests for Real-ESRGAN read-only readiness probe."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from realesrgan_probe import probe_realesrgan  # noqa: E402


class RealEsrganProbeTests(unittest.TestCase):
    def test_probe_policy_flags_and_schema(self) -> None:
        report = probe_realesrgan(base_url=None)
        self.assertTrue(report["ok"])
        self.assertTrue(report["auto_download_blocked"])
        self.assertTrue(report["auto_promote_blocked"])
        self.assertFalse(report["gfpgan_face_enhance_default"])
        self.assertEqual(report["weapon_id"], "realesrgan-animevideo-research")
        self.assertIn("backends", report)
        self.assertIn("weights", report)
        # execution_ready only when backend + fingerprints both present
        if report.get("execution_ready"):
            self.assertTrue(report.get("backend_ready"))
            self.assertTrue(report.get("weights_seen"))
            self.assertTrue((report.get("weights") or {}).get("fingerprints"))

    def test_probe_json_serializable(self) -> None:
        report = probe_realesrgan()
        payload = json.dumps(report, ensure_ascii=False)
        self.assertIn("realesrgan-readiness-probe", payload)

    def test_weight_dir_scan_finds_named_file(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "realesr-animevideov3.pth"
            fake.write_bytes(b"fake")
            report = probe_realesrgan(weight_dirs=[str(root)])
            self.assertTrue(report["weights_seen"])
            self.assertIn("realesr-animevideov3.pth", report["weights"]["preferred_present"])

    def test_comfy_hint_when_loader_present(self) -> None:
        with mock.patch(
            "realesrgan_probe._probe_comfy",
            return_value={
                "skipped": False,
                "ok": True,
                "base_url": "http://127.0.0.1:18188",
                "hint_classes_present": ["UpscaleModelLoader", "ImageUpscaleWithModel"],
                "upscale_loader_ready": True,
            },
        ) as mocked:
            report = probe_realesrgan(base_url="http://127.0.0.1:18188")
            mocked.assert_called_once()
            self.assertTrue(report["comfy"]["upscale_loader_ready"])
            self.assertTrue(report["backend_ready"])


if __name__ == "__main__":
    unittest.main()
