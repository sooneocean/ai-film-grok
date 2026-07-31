#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from i2v_provider import (  # noqa: E402
    FrwLtx23AudioProvider,
    FrwWanProvider,
    GrokI2VProvider,
    I2VProviderError,
    LocalComfyWan22Provider,
    SeedanceProvider,
    all_providers,
    for_endpoint,
    generate_with_fallback,
    get,
    is_technical_failure,
    provider_priority,
    provider_switch_receipt_is_valid,
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
        self.assertIn("frw-ltx23", names)
        self.assertIn("frw-wan", names)

    def test_action_provider_priority_is_ltx_grok_frw_wan_then_local(self) -> None:
        self.assertEqual(
            provider_priority(),
            ("frw-ltx23", "grok", "frw-wan", "comfy-wan22"),
        )

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
        self.assertEqual(for_endpoint("frw_img2video").name, "frw-img2video")
        self.assertIsInstance(for_endpoint("frw_ltx23_img2video_audio"), FrwLtx23AudioProvider)
        self.assertIsInstance(for_endpoint("frw_wan_i2v"), FrwWanProvider)
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

    def test_ltx23_audio_requires_film_canary_and_uses_native_audio_command(self) -> None:
        provider = get("frw-ltx23")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.assertFalse(provider.probe(root=root).available)
            receipt = root / "receipts" / "frw-ltx23-i2v-audio-canary.json"
            receipt.parent.mkdir()
            receipt.write_text(
                '{"ok":true,"output_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","full_decode_ok":true,"human_review":"approved"}',
                encoding="utf-8",
            )
            self.assertTrue(provider.probe(root=root).available)
        cmd = provider.build_command(
            keyframe=Path("/tmp/kf.png"), prompt="room tone", duration_sec=6
        )
        self.assertIn("img2video-audio", cmd)
        self.assertIn("--duration", cmd)

    def test_ltx23_primary_cannot_generate_without_a_valid_film_canary(self) -> None:
        import os
        from unittest import mock

        with (
            tempfile.TemporaryDirectory() as raw,
            mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "ltx23_primary"}, clear=False),
        ):
            root = Path(raw)
            with self.assertRaisesRegex(I2VProviderError, "I2V_PROVIDER_CHAIN_EXHAUSTED"):
                generate_with_fallback(
                    root=root,
                    shot_id="shot01",
                    keyframe=root / "keyframe.png",
                    prompt="room tone",
                    plan_sha256="a" * 64,
                )

    def test_ltx_not_ready_falls_through_to_ready_grok(self) -> None:
        import os
        from types import SimpleNamespace
        from unittest import mock

        class UnreadyLtx:
            name = "frw-ltx23"

            def probe(self, **_kwargs):
                return SimpleNamespace(available=False, reason="canary missing")

        class ReadyGrok:
            name = "grok"

            def probe(self, **_kwargs):
                return SimpleNamespace(available=True, reason="ready")

            def generate(self, **_kwargs):
                return {"ok": True, "provider": self.name}

        providers = {
            "frw-ltx23": UnreadyLtx(),
            "grok": ReadyGrok(),
        }
        with (
            tempfile.TemporaryDirectory() as raw,
            mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "ltx23_primary"}, clear=False),
            mock.patch(
                "i2v_provider.get",
                side_effect=lambda name: (
                    providers.get(name)
                    or SimpleNamespace(
                        name=name,
                        probe=lambda **_kwargs: SimpleNamespace(
                            available=False, reason="not ready"
                        ),
                    )
                ),
            ),
        ):
            result = generate_with_fallback(
                root=Path(raw),
                shot_id="shot01",
                keyframe=Path(raw) / "frame.png",
                prompt="action",
                plan_sha256="a" * 64,
            )
        self.assertEqual(result["route"], "grok_fallback")
        self.assertEqual(result["routing_attempts"][0]["provider"], "frw-ltx23")
        self.assertEqual(result["routing_attempts"][0]["status"], "not_ready")

    def test_technical_failure_uses_next_ready_provider_in_priority_order(self) -> None:
        import os
        from types import SimpleNamespace
        from unittest import mock

        class Provider:
            def __init__(self, name: str, *, ready: bool, error: str | None = None):
                self.name = name
                self.ready = ready
                self.error = error

            def probe(self, **_kwargs):
                return SimpleNamespace(
                    available=self.ready, reason="ready" if self.ready else "off"
                )

            def generate(self, **_kwargs):
                if self.error:
                    raise I2VProviderError(self.error)
                return {"ok": True, "provider": self.name}

        providers = {
            "frw-ltx23": Provider("frw-ltx23", ready=True, error="HTTP 503"),
            "grok": Provider("grok", ready=True, error="HTTP 503"),
            "frw-wan": Provider("frw-wan", ready=True),
            "comfy-wan22": Provider("comfy-wan22", ready=True),
        }
        with (
            tempfile.TemporaryDirectory() as raw,
            mock.patch.dict(
                os.environ,
                {
                    "AIFILM_I2V_PROFILE": "ltx23_primary",
                    "AIFILM_PROVIDER_SWITCH_RECEIPT_KEY": "k" * 32,
                },
                clear=False,
            ),
            mock.patch("i2v_provider.get", side_effect=lambda name: providers[name]),
        ):
            result = generate_with_fallback(
                root=Path(raw),
                shot_id="shot01",
                keyframe=Path(raw) / "frame.png",
                prompt="action",
                plan_sha256="b" * 64,
            )
            receipts = sorted(
                (Path(raw) / "receipts" / "provider-switches").glob("provider-switch-*.json")
            )
        self.assertEqual(result["route"], "frw-wan_fallback")
        self.assertEqual(
            [item["provider"] for item in result["routing_attempts"]],
            ["frw-ltx23", "grok", "frw-wan"],
        )
        self.assertEqual(
            [path.name.rsplit("-", 1)[0] for path in receipts],
            ["provider-switch-shot01-frw-ltx23-to-grok", "provider-switch-shot01-grok-to-frw-wan"],
        )
        with mock.patch.dict(
            os.environ,
            {"AIFILM_PROVIDER_SWITCH_RECEIPT_KEY": "k" * 32},
            clear=False,
        ):
            self.assertTrue(provider_switch_receipt_is_valid(result["provider_switch"]))

    def test_multiple_technical_fallbacks_preserve_each_signed_switch(self) -> None:
        import json
        import os
        from types import SimpleNamespace
        from unittest import mock

        class Provider:
            def __init__(self, name: str, error: str | None = None):
                self.name = name
                self.error = error

            def probe(self, **_kwargs):
                return SimpleNamespace(available=True, reason="ready")

            def generate(self, **_kwargs):
                if self.error:
                    raise I2VProviderError(self.error)
                return {"ok": True, "provider": self.name}

        providers = {
            "frw-ltx23": Provider("frw-ltx23", "HTTP 503"),
            "grok": Provider("grok", "HTTP 502"),
            "frw-wan": Provider("frw-wan"),
            "comfy-wan22": Provider("comfy-wan22"),
        }
        with (
            tempfile.TemporaryDirectory() as raw,
            mock.patch.dict(
                os.environ,
                {"AIFILM_PROVIDER_SWITCH_RECEIPT_KEY": "k" * 32},
                clear=False,
            ),
            mock.patch("i2v_provider.get", side_effect=lambda name: providers[name]),
        ):
            root = Path(raw)
            result = generate_with_fallback(
                root=root,
                shot_id="shot01",
                keyframe=root / "frame.png",
                prompt="action",
                plan_sha256="c" * 64,
            )
            self.assertEqual(
                [
                    (item["primary_provider"], item["fallback_provider"])
                    for item in result["provider_switches"]
                ],
                [("frw-ltx23", "grok"), ("grok", "frw-wan")],
            )
            for item in result["provider_switches"]:
                self.assertTrue(provider_switch_receipt_is_valid(item))
                self.assertTrue(Path(item["archive_path"]).is_file())
            routing = json.loads(
                (root / "receipts" / "i2v-routing.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(routing["provider_switch_sha256s"]), 2)

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

    def test_comfy_build_command_auto_routes_structured_weapon_intent(self) -> None:
        from unittest import mock

        provider = LocalComfyWan22Provider()
        with mock.patch.object(
            provider,
            "_base_url",
            return_value="http://192.168.88.52:8188",
        ):
            command = provider.build_command(
                keyframe=Path("/tmp/adult-keyframe.png"),
                prompt="Structured shot prompt.",
                duration_sec=3,
                out=Path("/tmp/out.mp4"),
                weapon_intent="adult-meat-motion",
                production_stage="pilot",
                allow_experimental=True,
                subject_basis="fictional_adults",
            )
        profile_index = command.index("--profile") + 1
        self.assertEqual(command[profile_index], "adult-general-experimental")
        self.assertIn("--subject-basis", command)

    def test_comfy_build_command_refuses_unpromoted_meat_production_weapon(self) -> None:
        from unittest import mock

        provider = LocalComfyWan22Provider()
        with mock.patch.object(
            provider,
            "_base_url",
            return_value="http://192.168.88.52:8188",
        ):
            with self.assertRaisesRegex(I2VProviderError, "no promoted Wan 2.2 weapon"):
                provider.build_command(
                    keyframe=Path("/tmp/adult-keyframe.png"),
                    prompt="Structured shot prompt.",
                    out=Path("/tmp/out.mp4"),
                    weapon_intent="adult-meat-motion",
                    production_stage="production",
                    allow_experimental=True,
                    subject_basis="fictional_adults",
                )

    def test_comfy_build_command_rejects_explicit_experimental_production_bypass(
        self,
    ) -> None:
        from unittest import mock

        provider = LocalComfyWan22Provider()
        with mock.patch.object(
            provider,
            "_base_url",
            return_value="http://192.168.88.52:8188",
        ):
            with self.assertRaisesRegex(I2VProviderError, "pilot-only"):
                provider.build_command(
                    keyframe=Path("/tmp/adult-keyframe.png"),
                    prompt="Structured shot prompt.",
                    out=Path("/tmp/out.mp4"),
                    profile="adult-general-experimental",
                    production_stage="production",
                    allow_experimental=True,
                    subject_basis="fictional_adults",
                )
            with self.assertRaisesRegex(I2VProviderError, "quarantined"):
                provider.build_command(
                    keyframe=Path("/tmp/adult-keyframe.png"),
                    prompt="Structured shot prompt.",
                    out=Path("/tmp/out.mp4"),
                    profile="adult-action-experimental",
                    production_stage="pilot",
                    allow_experimental=True,
                    subject_basis="fictional_adults",
                )

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

    def test_comfy_generate_rejects_promoted_experimental_receipt(self) -> None:
        import hashlib
        import json
        import os
        from types import SimpleNamespace
        from unittest import mock

        with tempfile.TemporaryDirectory() as raw:
            out = Path(raw) / "clip.mp4"
            keyframe = Path(raw) / "keyframe.png"
            keyframe.write_bytes(b"adult-keyframe")
            out.write_bytes(b"generated-video")
            receipt = out.with_suffix(".mp4.receipt.json")
            receipt.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "kind": "local-wan22-generation",
                        "ok": True,
                        "provider": "comfy-wan22",
                        "profile": "adult-general-experimental",
                        "prompt_id": "p-experimental",
                        "input_sha256": hashlib.sha256(b"adult-keyframe").hexdigest(),
                        "output": {
                            "path": str(out),
                            "bytes": out.stat().st_size,
                            "sha256": hashlib.sha256(b"generated-video").hexdigest(),
                        },
                        "models": [
                            "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
                            "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
                        ],
                        "loras": ["NSFW-22-H-e8.safetensors", "NSFW-22-L-e8.safetensors"],
                        "lora_sha256": {
                            "NSFW-22-H-e8.safetensors": "34e2144d3cd65360f97d09ccbe03e1c39a096df6c9234af5fe3899d1b63cda39",
                            "NSFW-22-L-e8.safetensors": "d6b783742f4d5fd63a0223ae1d5bf64fc995a6b408480ac2a00528ae0d4146db",
                        },
                        "experimental_assets_promoted": True,
                        "subject_basis": "fictional_adults",
                        "adult_attestation": True,
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
                    prompt="adult pilot",
                    out=out,
                    profile="adult-general-experimental",
                    production_stage="pilot",
                    allow_experimental=True,
                    subject_basis="fictional_adults",
                )
        self.assertFalse(result["ok"])
        self.assertIn("experimental promotion state mismatch", result["stderr"])

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

    def test_legacy_seedance_profile_maps_to_ltx_primary(self) -> None:
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "seedance_first"}):
            self.assertIsInstance(__import__("i2v_provider").preferred(), FrwLtx23AudioProvider)

    def test_only_technical_failure_routes_to_frw(self) -> None:
        import os
        from unittest import mock

        self.assertTrue(is_technical_failure("HTTP 503 service unavailable"))
        self.assertFalse(is_technical_failure({"task_id": "ambiguous"}))
        self.assertIsNone(
            route_after_failure(root=None, shot_id="s1", primary="grok", error="quality fail")
        )
        with mock.patch.dict(
            os.environ,
            {"AIFILM_PROVIDER_SWITCH_RECEIPT_KEY": "k" * 32},
        ):
            selected = route_after_failure(
                root=None,
                shot_id="s1",
                primary="grok",
                error="HTTP 503",
            )
            self.assertTrue(provider_switch_receipt_is_valid(selected[1]))
        self.assertIsNotNone(selected)
        self.assertEqual(selected[0].name, "frw-wan")

    def test_provider_switch_writer_requires_local_hmac_key(self) -> None:
        import json
        import os
        from unittest import mock

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(I2VProviderError, "RECEIPT_KEY"):
                    route_after_failure(
                        root=root,
                        shot_id="s1",
                        primary="grok",
                        error="HTTP 503",
                    )
            with mock.patch.dict(
                os.environ,
                {"AIFILM_PROVIDER_SWITCH_RECEIPT_KEY": "k" * 32},
                clear=True,
            ):
                selected = route_after_failure(
                    root=root,
                    shot_id="s1",
                    primary="grok",
                    error="HTTP 503 token=synthetic-secret-not-real",
                )
                stored = json.loads(
                    (root / "receipts" / "provider-switch-s1.json").read_text(encoding="utf-8")
                )
                self.assertTrue(provider_switch_receipt_is_valid(stored))
                self.assertEqual(stored["switch_hmac_sha256"], selected[1]["switch_hmac_sha256"])
                self.assertNotIn("synthetic-secret-not-real", repr(stored))
                archived = list(
                    (root / "receipts" / "provider-switches").glob(
                        "provider-switch-s1-grok-to-frw-wan-*.json"
                    )
                )
                self.assertEqual(len(archived), 1)
            with mock.patch.dict(
                os.environ,
                {"AIFILM_PROVIDER_SWITCH_RECEIPT_KEY": "z" * 32},
                clear=True,
            ):
                self.assertFalse(provider_switch_receipt_is_valid(stored))

    def test_repeated_switches_are_preserved_as_distinct_signed_events(self) -> None:
        import json
        import os
        from unittest import mock

        with (
            tempfile.TemporaryDirectory() as raw,
            mock.patch.dict(
                os.environ,
                {"AIFILM_PROVIDER_SWITCH_RECEIPT_KEY": "k" * 32},
                clear=True,
            ),
        ):
            root = Path(raw)
            route_after_failure(root=root, shot_id="s1", primary="grok", error="HTTP 503")
            route_after_failure(root=root, shot_id="s1", primary="grok", error="HTTP 504")
            archived = sorted(
                (root / "receipts" / "provider-switches").glob(
                    "provider-switch-s1-grok-to-frw-wan-*.json"
                )
            )
            self.assertEqual(len(archived), 2)
            receipts = [json.loads(path.read_text(encoding="utf-8")) for path in archived]
            self.assertEqual({item["error"] for item in receipts}, {"http 503", "http 504"})
            self.assertEqual(len({item["event_id"] for item in receipts}), 2)
            self.assertTrue(all(provider_switch_receipt_is_valid(item) for item in receipts))

    def test_frw_wan_canary_requires_explicit_wan_model_identity(self) -> None:
        import json

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            receipt = root / "receipts" / "frw-wan-i2v-canary.json"
            receipt.parent.mkdir()
            payload = {
                "ok": True,
                "model": "not-wan",
                "output_sha256": "a" * 64,
                "full_decode_ok": True,
                "human_review": "approved",
            }
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            self.assertFalse(get("frw-wan").probe(root=root).available)
            payload["model"] = "wan2.2-i2v"
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            self.assertTrue(get("frw-wan").probe(root=root).available)

    def test_frw_wan_generation_fails_closed_without_response_model_identity(self) -> None:
        import json
        from unittest import mock

        provider = get("frw-wan")
        with mock.patch(
            "i2v_provider.SeedanceProvider.generate",
            return_value={"ok": True, "stdout": json.dumps({"data": {"id": "task-1"}})},
        ):
            result = provider.generate(keyframe=Path("/tmp/keyframe.png"), prompt="action")
        self.assertFalse(result["ok"])
        self.assertEqual(result["stderr"], "FRW_WAN_MODEL_IDENTITY_UNVERIFIED")

    def test_provider_switch_rejects_pathlike_shot_id(self) -> None:
        import os
        from unittest import mock

        with mock.patch.dict(
            os.environ,
            {"AIFILM_PROVIDER_SWITCH_RECEIPT_KEY": "k" * 32},
            clear=True,
        ):
            with self.assertRaisesRegex(I2VProviderError, "SHOT_ID_INVALID"):
                route_after_failure(
                    root=Path(tempfile.gettempdir()),
                    shot_id="../receipt",
                    primary="grok",
                    error="HTTP 503",
                )

    def test_fallback_binds_the_executed_plan_to_its_switch_receipt(self) -> None:
        import os
        from unittest import mock

        class Provider:
            def __init__(self, name: str, *, ready: bool, error: str | None = None):
                self.name = name
                self.ready = ready
                self.error = error

            def probe(self, **_kwargs):
                from types import SimpleNamespace

                return SimpleNamespace(
                    available=self.ready, reason="ready" if self.ready else "off"
                )

            def generate(self, **_kwargs):
                if self.error:
                    raise I2VProviderError(self.error)
                return {"ok": True, "provider": self.name}

        providers = {
            "frw-ltx23": Provider("frw-ltx23", ready=True, error="HTTP 503"),
            "grok": Provider("grok", ready=True),
            "frw-wan": Provider("frw-wan", ready=False),
            "comfy-wan22": Provider("comfy-wan22", ready=False),
        }
        with (
            tempfile.TemporaryDirectory() as raw,
            mock.patch.dict(
                os.environ,
                {
                    "AIFILM_I2V_PROFILE": "ltx23_primary",
                    "AIFILM_PROVIDER_SWITCH_RECEIPT_KEY": "k" * 32,
                },
                clear=True,
            ),
            mock.patch("i2v_provider.get", side_effect=lambda name: providers[name]),
        ):
            result = generate_with_fallback(
                root=Path(raw),
                shot_id="shot01",
                keyframe=Path(raw) / "frame.png",
                prompt="test",
                plan_sha256="a" * 64,
            )
            assert result["route"] == "grok_fallback"
            assert result["provider_switch"]["plan_sha256"] == "a" * 64
            assert provider_switch_receipt_is_valid(result["provider_switch"])

    def test_preferred_returns_registered(self) -> None:
        """preferred() never raises and returns a registered provider."""
        from i2v_provider import preferred

        provider = preferred()
        self.assertIn(provider.name, all_providers())


if __name__ == "__main__":
    unittest.main()
