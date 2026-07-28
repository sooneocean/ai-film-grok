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
    LocalComfyWan22Provider,
    SeedanceProvider,
    all_providers,
    for_endpoint,
    get,
    is_technical_failure,
    registry_report,
    route_after_failure,
)


class I2VProviderTests(unittest.TestCase):
    def test_registry_has_grok_and_seedance(self) -> None:
        """DoD: cloud and explicit local providers are registered."""
        names = all_providers()
        self.assertIn("grok", names)
        self.assertIn("seedance", names)
        self.assertIn("comfy-wan22", names)

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
        self.assertIsInstance(for_endpoint("local_wan22_i2v"), LocalComfyWan22Provider)
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

    def test_comfy_build_command_uses_pinned_runtime_and_long_timeout(self) -> None:
        import os
        from unittest import mock

        with mock.patch.dict(
            os.environ,
            {"AIFILM_COMFYUI_BASE_URL": "http://192.168.88.52:8188"},
        ):
            provider = get("comfy-wan22")
            cmd = provider.build_command(
                keyframe=Path("/tmp/kf.png"),
                prompt="camera move",
                out="/tmp/clip.mp4",
            )
        self.assertEqual(cmd[0], sys.executable)
        self.assertIn("--timeout", cmd)
        self.assertEqual(cmd[cmd.index("--timeout") + 1], "1800")
        self.assertEqual(provider.command_timeout_sec, 1830)

    def test_comfy_generate_reads_hash_bound_receipt(self) -> None:
        import hashlib
        import json
        import os
        from types import SimpleNamespace
        from unittest import mock

        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw) / "clip.mp4"
            keyframe = Path(raw) / "keyframe.png"
            keyframe.write_bytes(b"keyframe")
            out.write_bytes(b"generated-video")
            input_sha = hashlib.sha256(keyframe.read_bytes()).hexdigest()
            output_sha = hashlib.sha256(out.read_bytes()).hexdigest()
            receipt = out.with_suffix(".mp4.receipt.json")
            receipt.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "local-wan22-generation",
                        "ok": True,
                        "provider": "comfy-wan22",
                        "profile": "official",
                        "prompt_id": "p-1",
                        "input_sha256": input_sha,
                        "output": {
                            "path": str(out),
                            "bytes": out.stat().st_size,
                            "sha256": output_sha,
                        },
                        "models": [
                            "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
                            "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.dict(
                    os.environ,
                    {"AIFILM_COMFYUI_BASE_URL": "http://192.168.88.52:8188"},
                ),
                mock.patch(
                    "i2v_provider.subprocess.run",
                    return_value=SimpleNamespace(returncode=0, stdout="{}", stderr=""),
                ),
            ):
                result = get("comfy-wan22").generate(
                    keyframe=keyframe,
                    prompt="camera move",
                    out=out,
                )
        self.assertTrue(result["ok"])
        self.assertEqual(result["prompt_id"], "p-1")
        self.assertEqual(result["output_sha256"], output_sha)

    def test_comfy_generate_binds_receipt_to_prelaunch_input_bytes(self) -> None:
        import hashlib
        import json
        import os
        from types import SimpleNamespace
        from unittest import mock

        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw) / "clip.mp4"
            keyframe = Path(raw) / "keyframe.png"
            original = b"uploaded-keyframe"
            keyframe.write_bytes(original)
            out.write_bytes(b"generated-video")
            input_sha = hashlib.sha256(original).hexdigest()
            output_sha = hashlib.sha256(out.read_bytes()).hexdigest()
            receipt = out.with_suffix(".mp4.receipt.json")

            def mutate_after_launch(*_args: object, **_kwargs: object) -> SimpleNamespace:
                receipt.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "kind": "local-wan22-generation",
                            "ok": True,
                            "provider": "comfy-wan22",
                            "profile": "official",
                            "prompt_id": "p-1",
                            "input_sha256": input_sha,
                            "output": {
                                "path": str(out),
                                "bytes": out.stat().st_size,
                                "sha256": output_sha,
                            },
                            "models": [
                                "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
                                "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                keyframe.write_bytes(b"changed-after-upload")
                return SimpleNamespace(returncode=0, stdout="{}", stderr="")

            with (
                mock.patch.dict(
                    os.environ,
                    {"AIFILM_COMFYUI_BASE_URL": "http://192.168.88.52:8188"},
                ),
                mock.patch("i2v_provider.subprocess.run", side_effect=mutate_after_launch),
            ):
                result = get("comfy-wan22").generate(
                    keyframe=keyframe,
                    prompt="camera move",
                    out=out,
                )
        self.assertTrue(result["ok"])
        self.assertEqual(result["input_sha256"], input_sha)

    def test_comfy_generate_rejects_forged_receipt(self) -> None:
        import json
        import os
        from types import SimpleNamespace
        from unittest import mock

        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw) / "missing.mp4"
            receipt = out.with_suffix(".mp4.receipt.json")
            receipt.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "local-wan22-generation",
                        "ok": True,
                        "provider": "comfy-wan22",
                        "profile": "official",
                        "prompt_id": "p-forged",
                        "input_sha256": "forged-input",
                        "output": {
                            "path": str(out),
                            "bytes": 123,
                            "sha256": "forged-output",
                        },
                        "models": ["fake"],
                    }
                ),
                encoding="utf-8",
            )
            with (
                mock.patch.dict(
                    os.environ,
                    {"AIFILM_COMFYUI_BASE_URL": "http://192.168.88.52:8188"},
                ),
                mock.patch(
                    "i2v_provider.subprocess.run",
                    return_value=SimpleNamespace(returncode=0, stdout="{}", stderr=""),
                ),
            ):
                result = get("comfy-wan22").generate(
                    keyframe=Path(raw) / "missing-keyframe.png",
                    prompt="camera move",
                    out=out,
                )
        self.assertFalse(result["ok"])
        self.assertIn("verification failed", result["stderr"])

    def test_unknown_provider_raises(self) -> None:
        with self.assertRaises(I2VProviderError):
            get("nonexistent")

    def test_registry_report(self) -> None:
        """registry_report lists all providers + active one."""
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"AIFILM_COMFYUI_BASE_URL": ""}):
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
        self.assertIsNone(
            route_after_failure(root=None, shot_id="s1", primary="grok", error="quality fail")
        )
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
