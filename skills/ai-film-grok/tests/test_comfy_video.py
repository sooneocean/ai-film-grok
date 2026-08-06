from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from comfy_video import (  # noqa: E402
    WAN22_ADULT_ACTION_EXPERIMENTAL_PROFILE,
    WAN22_ADULT_PROFILE,
    WAN22_GENERAL_ADULT_EXPERIMENTAL_PROFILE,
    WAN22_OFFICIAL_PROFILE,
    ComfyVideoError,
    _json_request,
    _wait_for_completion_ws,
    apply_workflow_overrides,
    assert_local_only_workflow,
    assert_submission_capacity,
    build_wan22_i2v_prompt,
    cancel_prompt,
    download_result,
    free_memory,
    generate,
    inventory,
    load_api_workflow,
    normalize_base_url,
    probe,
    queue_status,
    resolve_wan22_profile,
    select_wan22_weapon,
    submission_capacity,
    submit,
    upload_image,
    validate_adult_request,
    wait_for_result,
    workflow_sha256,
)


class ComfyVideoTests(unittest.TestCase):
    def setUp(self) -> None:
        self._driver_vram_fallback = os.environ.pop("AIFILM_COMFY_DRIVER_VRAM_FALLBACK", None)

    def tearDown(self) -> None:
        if self._driver_vram_fallback is None:
            os.environ.pop("AIFILM_COMFY_DRIVER_VRAM_FALLBACK", None)
        else:
            os.environ["AIFILM_COMFY_DRIVER_VRAM_FALLBACK"] = self._driver_vram_fallback

    def test_local_wan_generation_is_retired_before_any_network_call(self) -> None:
        with self.assertRaisesRegex(ComfyVideoError, "WAN22_I2V_RETIRED"):
            generate(
                base_url="http://127.0.0.1:8188",
                image=Path("frame.png"),
                prompt="movement",
                out=Path("clip.mp4"),
                width=704,
                height=1280,
                duration_sec=5,
                seed=1,
                turbo=False,
                profile=WAN22_OFFICIAL_PROFILE,
                subject_basis="adult",
            )

    def test_armory_auto_routes_general_i2v_to_official_quality(self) -> None:
        selection = select_wan22_weapon(intent="general", stage="production")
        self.assertEqual(selection["profile"]["name"], "official")
        self.assertEqual(selection["weapon_status"], "promoted")
        self.assertFalse(selection["requires_adult_attestation"])

    def test_armory_auto_routes_adult_intimacy_to_attested_baseline(self) -> None:
        selection = select_wan22_weapon(intent="adult-intimacy", stage="production")
        self.assertEqual(selection["profile"]["name"], "adult-motion")
        self.assertEqual(selection["weapon_status"], "promoted-baseline")
        self.assertTrue(selection["requires_adult_attestation"])

    def test_armory_auto_routes_meat_pilot_to_verified_experimental_pair(self) -> None:
        selection = select_wan22_weapon(
            intent="adult-meat-motion",
            stage="pilot",
            allow_experimental=True,
        )
        self.assertEqual(selection["profile"]["name"], "adult-general-experimental")
        self.assertEqual(selection["weapon_status"], "experimental")
        self.assertTrue(selection["requires_human_approval"])

    def test_armory_refuses_unproven_meat_weapon_for_production(self) -> None:
        with self.assertRaisesRegex(ComfyVideoError, "no promoted Wan 2.2 weapon"):
            select_wan22_weapon(
                intent="adult-meat-motion",
                stage="production",
                allow_experimental=True,
            )

    def test_armory_keeps_rejected_action_pair_out_of_auto_routing(self) -> None:
        for intent, stage, allow_experimental in (
            ("general", "production", False),
            ("adult-intimacy", "production", False),
            ("adult-meat-motion", "pilot", True),
        ):
            selection = select_wan22_weapon(
                intent=intent,
                stage=stage,
                allow_experimental=allow_experimental,
            )
            self.assertNotEqual(
                selection["profile"]["name"],
                "adult-action-experimental",
            )

    def test_explicit_experimental_profiles_cannot_bypass_pilot_gate(self) -> None:
        with self.assertRaisesRegex(ComfyVideoError, "quarantined"):
            resolve_wan22_profile(
                "adult-action-experimental",
                stage="pilot",
                allow_experimental=True,
            )
        with self.assertRaisesRegex(ComfyVideoError, "pilot-only"):
            resolve_wan22_profile(
                "adult-general-experimental",
                stage="production",
                allow_experimental=True,
            )
        with self.assertRaisesRegex(ComfyVideoError, "requires --allow-experimental"):
            resolve_wan22_profile(
                "adult-general-experimental",
                stage="pilot",
                allow_experimental=False,
            )
        selected = resolve_wan22_profile(
            "adult-general-experimental",
            stage="pilot",
            allow_experimental=True,
        )
        self.assertEqual(selected["name"], "adult-general-experimental")

    @patch("comfy_video._json_request")
    def test_probe_requires_exact_general_experimental_lora_hashes(
        self,
        request: MagicMock,
    ) -> None:
        required_diffusion = [
            WAN22_OFFICIAL_PROFILE["high"],
            WAN22_OFFICIAL_PROFILE["low"],
        ]
        required_loras = [
            WAN22_GENERAL_ADULT_EXPERIMENTAL_PROFILE["high_lora"],
            WAN22_GENERAL_ADULT_EXPERIMENTAL_PROFILE["low_lora"],
        ]

        def response(_base_url: str, route: str, **_kwargs: object) -> object:
            if route == "/system_stats":
                return {"system": {"comfyui_version": "0.22.0"}, "devices": []}
            if route == "/models/diffusion_models":
                return required_diffusion
            if route == "/models/loras":
                return required_loras
            if route == "/models/text_encoders":
                return ["umt5_xxl_fp8_e4m3fn_scaled.safetensors"]
            if route == "/models/vae":
                return ["wan_2.1_vae.safetensors"]
            if route.startswith("/pysssss/metadata/"):
                return {"pysssss.sha256": "0" * 64}
            raise AssertionError(route)

        request.side_effect = response
        report = probe("https://192.168.88.52:8188")
        self.assertFalse(report["profiles"]["adult_general_experimental"])
        self.assertFalse(report["experimental_adult_assets"]["general_wan22_pair_hashes_verified"])

    @patch("comfy_video._OPENER.open")
    def test_json_request_accepts_empty_success_body(self, open_request: MagicMock) -> None:
        response = MagicMock()
        response.read.return_value = b""
        open_request.return_value.__enter__.return_value = response
        self.assertEqual(
            _json_request(
                "https://192.168.88.52:8188",
                "/free",
                method="POST",
                payload={"free_memory": True},
            ),
            {},
        )

    @patch("comfy_video._OPENER.open")
    def test_json_request_adds_broker_auth_without_echoing_it(
        self, open_request: MagicMock
    ) -> None:
        response = MagicMock()
        response.read.return_value = b"{}"
        open_request.return_value.__enter__.return_value = response
        previous = os.environ.get("AIFILM_COMFY_BROKER_TOKEN")
        os.environ["AIFILM_COMFY_BROKER_TOKEN"] = "t" * 32
        try:
            _json_request("http://127.0.0.1:18188", "/system_stats")
        finally:
            if previous is None:
                os.environ.pop("AIFILM_COMFY_BROKER_TOKEN", None)
            else:
                os.environ["AIFILM_COMFY_BROKER_TOKEN"] = previous
        request = open_request.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer " + "t" * 32)

    @patch("comfy_video._json_request")
    def test_submit_binds_registered_weapon_checksum(self, request: MagicMock) -> None:
        request.return_value = {"prompt_id": "prompt-1"}
        graph = {"1": {"class_type": "LoadImage", "inputs": {"image": "x.png"}}}
        with patch("comfy_video.assert_submission_capacity"):
            with patch("comfy_video._submission_admission_lock") as lock:
                lock.return_value.__enter__.return_value = None
                lock.return_value.__exit__.return_value = False
                submit("http://127.0.0.1:18188", graph, weapon_id="fantasy-talking-6step-pilot")
        headers = request.call_args.kwargs["extra_headers"]
        self.assertEqual(headers["X-AIFilm-Weapon-ID"], "fantasy-talking-6step-pilot")
        self.assertEqual(headers["X-AIFilm-Workflow-SHA256"], workflow_sha256(graph))

    def test_private_comfyui_url_is_accepted(self) -> None:
        self.assertEqual(
            normalize_base_url("https://192.168.88.52:8188/"),
            "https://192.168.88.52:8188",
        )
        self.assertEqual(normalize_base_url("http://127.0.0.1:8188"), "http://127.0.0.1:8188")
        self.assertEqual(normalize_base_url("https://[fd00::1]:8188"), "https://[fd00::1]:8188")

    def test_public_or_credentialed_url_is_rejected(self) -> None:
        credentialed_url = "http://" + "user" + ":" + "pass" + "@192.168.88.52:8188"
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("https://example.com")
        with self.assertRaises(ComfyVideoError):
            normalize_base_url(credentialed_url)
        with self.assertRaisesRegex(ComfyVideoError, "HTTPS.*loopback"):
            normalize_base_url("http://192.168.88.52:8188")
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("http://0.0.0.0:8188")
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("http://169.254.169.254:8188")
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("http://192.0.0.1:8188")
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("http://[fe80::1]:8188")
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("https://192.168.88.52:8188?token=secret")
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("https://192.168.88.52:8188/#fragment")

    def test_official_turbo_graph_has_required_models_and_inputs(self) -> None:
        graph = build_wan22_i2v_prompt(
            image_name="canary.jpg",
            prompt="Two clearly adult fictional performers move through a choreographed scene.",
            width=480,
            height=704,
            duration_sec=3,
            seed=1234,
            turbo=True,
            profile=WAN22_OFFICIAL_PROFILE,
        )
        serialized = str(graph)
        self.assertIn("canary.jpg", serialized)
        self.assertIn("wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", serialized)
        self.assertIn("wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", serialized)
        self.assertIn("wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors", serialized)
        self.assertEqual(graph["wan_i2v"]["inputs"]["width"], 480)
        self.assertEqual(graph["wan_i2v"]["inputs"]["height"], 704)
        self.assertEqual(graph["wan_i2v"]["inputs"]["length"], 49)
        self.assertEqual(graph["sampler_high"]["inputs"]["steps"], 4)
        self.assertEqual(graph["sampler_high"]["inputs"]["end_at_step"], 2)

    def test_official_quality_graph_does_not_load_lightning_loras(self) -> None:
        graph = build_wan22_i2v_prompt(
            image_name="canary.jpg",
            prompt="Two clearly adult fictional performers move through a choreographed scene.",
            width=480,
            height=704,
            duration_sec=1,
            seed=1234,
            turbo=False,
            profile=WAN22_OFFICIAL_PROFILE,
        )
        self.assertNotIn("lora_high", graph)
        self.assertNotIn("lora_low", graph)
        self.assertEqual(graph["model_high"]["inputs"]["model"], ["unet_high", 0])
        self.assertEqual(graph["model_low"]["inputs"]["model"], ["unet_low", 0])

    def test_adult_profile_uses_verified_official_pair_without_unverified_lora(
        self,
    ) -> None:
        graph = build_wan22_i2v_prompt(
            image_name="licensed.jpg",
            prompt="Two consenting adult fictional performers in an intimate dramatic scene.",
            width=480,
            height=704,
            duration_sec=3,
            seed=42,
            turbo=False,
            profile=WAN22_ADULT_PROFILE,
        )
        serialized = str(graph)
        self.assertIn("wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", serialized)
        self.assertIn("wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", serialized)
        self.assertNotIn("wan22Enhanced_NSFW_FastMove", serialized)
        self.assertNotIn("wan_cumshot_i2v.safetensors", serialized)

    def test_experimental_adult_action_profile_loads_verified_noise_pair(self) -> None:
        graph = build_wan22_i2v_prompt(
            image_name="licensed.jpg",
            prompt="Two consenting adult fictional performers in a choreographed dance.",
            width=480,
            height=704,
            duration_sec=1,
            seed=42,
            turbo=False,
            profile=WAN22_ADULT_ACTION_EXPERIMENTAL_PROFILE,
        )
        self.assertEqual(
            graph["lora_high"]["inputs"]["lora_name"],
            "wan22-mouthfull-140epoc-high-k3nk.safetensors",
        )
        self.assertEqual(
            graph["lora_low"]["inputs"]["lora_name"],
            "wan22-mouthfull-152epoc-low-k3nk.safetensors",
        )
        self.assertEqual(graph["model_high"]["inputs"]["model"], ["lora_high", 0])
        self.assertEqual(graph["model_low"]["inputs"]["model"], ["lora_low", 0])
        self.assertEqual(graph["sampler_high"]["inputs"]["steps"], 20)

    def test_general_adult_experimental_profile_uses_recommended_strength(self) -> None:
        graph = build_wan22_i2v_prompt(
            image_name="licensed.jpg",
            prompt="nsfwsks, two consenting adult fictional performers dance.",
            width=480,
            height=704,
            duration_sec=1,
            seed=42,
            turbo=False,
            profile=WAN22_GENERAL_ADULT_EXPERIMENTAL_PROFILE,
        )
        self.assertEqual(graph["lora_high"]["inputs"]["lora_name"], "NSFW-22-H-e8.safetensors")
        self.assertEqual(graph["lora_low"]["inputs"]["lora_name"], "NSFW-22-L-e8.safetensors")
        self.assertEqual(graph["lora_high"]["inputs"]["strength_model"], 0.9)
        self.assertEqual(graph["lora_low"]["inputs"]["strength_model"], 0.9)

    def test_adult_profile_requires_authorized_adult_attestation(self) -> None:
        with self.assertRaises(ComfyVideoError):
            validate_adult_request(
                prompt="Two adults in an intimate scene.",
                subject_basis="",
            )
        validate_adult_request(
            prompt="Two consenting adult fictional performers in an intimate scene.",
            subject_basis="fictional_adults",
        )
        validate_adult_request(
            prompt="Two consenting adult performers in an intimate scene.",
            subject_basis="licensed_adults",
        )

    def test_minor_signals_fail_closed(self) -> None:
        for text in (
            "schoolgirl in a sexual scene",
            "underage character",
            "teen-looking performer",
            "loli character",
            "未成年の少女 sexual scene",
            "女子高生 intimate scene",
            "a 17-year-old performer",
            "１７歳 performer",
            "young girl intimate scene",
            "未成年角色",
            "高中生 intimate scene",
        ):
            with self.subTest(text=text), self.assertRaises(ComfyVideoError):
                validate_adult_request(prompt=text, subject_basis="fictional_adults")

    def test_load_api_workflow_rejects_save_format_or_unsafe_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_format = root / "save.json"
            save_format.write_text(
                '{"nodes": [], "links": [], "groups": []}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ComfyVideoError, "API format"):
                load_api_workflow(save_format)

            api_format = root / "api.json"
            api_format.write_text(
                '{"1":{"class_type":"KSampler","inputs":{"seed":1}}}',
                encoding="utf-8",
            )
            self.assertEqual(load_api_workflow(api_format)["1"]["class_type"], "KSampler")

    def test_workflow_overrides_are_typed_and_cannot_add_unknown_inputs(self) -> None:
        graph = {
            "1": {
                "class_type": "KSampler",
                "inputs": {"seed": 1, "cfg": 3.5},
            }
        }
        updated = apply_workflow_overrides(graph, {"1": {"seed": 99}})
        self.assertEqual(updated["1"]["inputs"]["seed"], 99)
        self.assertEqual(graph["1"]["inputs"]["seed"], 1)
        with self.assertRaisesRegex(ComfyVideoError, "unknown input"):
            apply_workflow_overrides(graph, {"1": {"surprise": True}})
        with self.assertRaisesRegex(ComfyVideoError, "type mismatch"):
            apply_workflow_overrides(graph, {"1": {"seed": "not-an-integer"}})
        with self.assertRaisesRegex(ComfyVideoError, "type mismatch"):
            apply_workflow_overrides(graph, {"1": {"cfg": {"unexpected": "object"}}})

    def test_workflow_hash_is_canonical(self) -> None:
        first = {"2": {"inputs": {"b": 2, "a": 1}, "class_type": "Node"}}
        second = {"2": {"class_type": "Node", "inputs": {"a": 1, "b": 2}}}
        self.assertEqual(workflow_sha256(first), workflow_sha256(second))

    def test_upload_rejects_multipart_header_injection_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / 'bad"name.png'
            image.write_bytes(b"not-an-image")
            with self.assertRaisesRegex(ComfyVideoError, "unsafe"):
                upload_image("https://192.168.88.52:8188", image)

    @patch("comfy_video._json_request")
    def test_local_only_validation_blocks_paid_api_nodes(self, request: MagicMock) -> None:
        request.return_value = {
            "ByteDanceImageToVideoNode": {
                "api_node": True,
                "category": "api node/video/ByteDance",
            }
        }
        graph = {
            "1": {
                "class_type": "ByteDanceImageToVideoNode",
                "inputs": {},
            }
        }
        with self.assertRaisesRegex(ComfyVideoError, "external API node"):
            assert_local_only_workflow("https://192.168.88.52:8188", graph)

    @patch("comfy_video._json_request")
    def test_local_only_validation_detects_credentialed_llm_helper(
        self,
        request: MagicMock,
    ) -> None:
        request.return_value = {
            "OpenAIHelper": {
                "input": {
                    "required": {
                        "endpoint": ["STRING", {}],
                        "api_key": ["STRING", {}],
                    }
                },
                "category": "ListHelper/LLM",
                "python_module": "custom_nodes.ComfyUI-ListHelper",
            }
        }
        graph = {"1": {"class_type": "OpenAIHelper", "inputs": {}}}
        with self.assertRaisesRegex(ComfyVideoError, "external API node"):
            assert_local_only_workflow("https://192.168.88.52:8188", graph)

    @patch("comfy_video._json_request")
    def test_local_only_validation_rejects_unknown_or_custom_nodes(
        self,
        request: MagicMock,
    ) -> None:
        graph = {"1": {"class_type": "OpenAIImageNode", "inputs": {}}}
        request.return_value = {}
        with self.assertRaisesRegex(ComfyVideoError, "metadata unavailable"):
            assert_local_only_workflow("https://192.168.88.52:8188", graph)

        request.return_value = {
            "OpenAIImageNode": {
                "category": "image/generate",
                "python_module": "custom_nodes.openai",
            }
        }
        with self.assertRaisesRegex(ComfyVideoError, "external API node"):
            assert_local_only_workflow("https://192.168.88.52:8188", graph)

    @patch("comfy_video._json_request")
    def test_local_only_validation_accepts_core_local_node(self, request: MagicMock) -> None:
        request.return_value = {
            "KSampler": {
                "category": "sampling",
                "python_module": "nodes",
                "output_node": False,
            }
        }
        assert_local_only_workflow(
            "https://192.168.88.52:8188",
            {"1": {"class_type": "KSampler", "inputs": {}}},
        )

    @patch("comfy_video._json_request")
    def test_inventory_is_bounded_and_reports_queue_and_models(self, request: MagicMock) -> None:
        def response(
            _base_url: str,
            route: str,
            **_kwargs: object,
        ) -> object:
            return {
                "/system_stats": {
                    "system": {"comfyui_version": "0.22.0", "ram_free": 5},
                    "devices": [{"name": "RTX 5090", "vram_total": 32, "vram_free": 17}],
                },
                "/features": {"max_upload_size": 100},
                "/models": ["checkpoints", "diffusion_models"],
                "/models/checkpoints": ["a.safetensors"],
                "/models/diffusion_models": ["wan.safetensors", "ltx.safetensors"],
                "/queue": {"queue_running": [], "queue_pending": [["x", "prompt-1"]]},
            }[route]

        request.side_effect = response
        report = inventory("https://192.168.88.52:8188")
        self.assertEqual(report["model_counts"]["diffusion_models"], 2)
        self.assertEqual(report["queue"]["pending"], 1)
        self.assertNotIn("object_info", report)

    @patch("comfy_video._json_request")
    def test_submission_capacity_accepts_idle_healthy_node(self, request: MagicMock) -> None:
        request.side_effect = [
            {
                "system": {"ram_free": 16 * 1024**3},
                "devices": [
                    {
                        "name": "RTX 5090",
                        "type": "cuda",
                        "vram_total": 32 * 1024**3,
                        "vram_free": 28 * 1024**3,
                    }
                ],
            },
            {"queue_running": [], "queue_pending": []},
        ]
        report = submission_capacity("https://192.168.88.52:8188")
        self.assertTrue(report["ok"])
        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["blockers"], [])

    @patch.dict(
        os.environ,
        {
            "AIFILM_COMFY_DRIVER_VRAM_FALLBACK": "1",
            "AIFILM_COMFY_SSH_TARGET": "user@private-node",
            "AIFILM_COMFY_SSH_KEY": "/tmp/private-key",
            "AIFILM_COMFY_SSH_KNOWN_HOSTS": "/tmp/known-hosts",
            "AIFILM_COMFY_SSH_HOSTKEY_ALIAS": "private-node",
            "AIFILM_COMFY_SSH_EXPECTED_HOSTNAME": "private-node",
        },
        clear=False,
    )
    @patch("comfy_video.subprocess.run")
    @patch("comfy_video._json_request")
    def test_submission_capacity_uses_authenticated_driver_vram_when_comfy_is_stale(
        self,
        request: MagicMock,
        run: MagicMock,
    ) -> None:
        request.side_effect = [
            {
                "system": {"ram_free": 16 * 1024**3},
                "devices": [
                    {
                        "name": "RTX 5090",
                        "type": "cuda",
                        "vram_total": 32 * 1024**3,
                        "vram_free": 20 * 1024**3,
                    }
                ],
            },
            {"queue_running": [], "queue_pending": []},
        ]
        run.side_effect = [
            MagicMock(returncode=0, stdout="123\n"),
            MagicMock(
                returncode=0,
                stdout=(
                    "ssh -fN -o HostKeyAlias=private-node "
                    "-L 127.0.0.1:18188:127.0.0.1:8188 user@private-node\n"
                ),
            ),
            MagicMock(
                returncode=0,
                stdout=(
                    '{"hostname":"private-node","comfy_version":"","python_version":"",'
                    '"gpu_name":"NVIDIA GeForce RTX 5090","gpu_total":34359738368,'
                    '"gpu_free_mib":"31320"}\n'
                ),
            ),
        ]

        report = submission_capacity("http://127.0.0.1:18188")

        self.assertTrue(report["ok"])
        self.assertEqual(report["observed"]["device"]["vram_source"], "nvidia-smi-via-ssh")
        self.assertEqual(report["observed"]["device"]["comfy_vram_free_bytes"], 20 * 1024**3)
        self.assertEqual(report["observed"]["device"]["driver_vram_free_bytes"], 31320 * 1024**2)

    @patch.dict(
        os.environ,
        {
            "AIFILM_COMFY_DRIVER_VRAM_FALLBACK": "1",
            "AIFILM_COMFY_SSH_TARGET": "user@private-node",
            "AIFILM_COMFY_SSH_KEY": "/tmp/private-key",
            "AIFILM_COMFY_SSH_KNOWN_HOSTS": "/tmp/known-hosts",
            "AIFILM_COMFY_SSH_HOSTKEY_ALIAS": "private-node",
            "AIFILM_COMFY_SSH_EXPECTED_HOSTNAME": "private-node",
        },
        clear=False,
    )
    @patch("comfy_video.subprocess.run")
    @patch("comfy_video._json_request")
    def test_submission_capacity_soft_falls_back_when_driver_probe_fails(
        self,
        request: MagicMock,
        run: MagicMock,
    ) -> None:
        """Driver probe failure must not block when ComfyUI already reported free VRAM."""
        request.side_effect = [
            {
                "system": {"ram_free": 16 * 1024**3},
                "devices": [{"name": "RTX 5090", "type": "cuda", "vram_free": 28 * 1024**3}],
            },
            {"queue_running": [], "queue_pending": []},
        ]
        run.side_effect = [
            MagicMock(returncode=0, stdout="123\n"),
            MagicMock(
                returncode=0,
                stdout=(
                    "ssh -fN -o HostKeyAlias=private-node "
                    "-L 127.0.0.1:18188:127.0.0.1:8188 user@private-node\n"
                ),
            ),
            MagicMock(returncode=1, stdout=""),
        ]

        report = submission_capacity("http://127.0.0.1:18188")

        self.assertTrue(report["ok"])
        self.assertEqual(report["blockers"], [])
        self.assertEqual(report["observed"]["device"]["vram_source"], "comfyui")
        self.assertIn(
            "SSH probe returned invalid data",
            str(report["observed"]["device"]["driver_vram_probe_error"] or ""),
        )

    @patch.dict(
        os.environ,
        {
            "AIFILM_COMFY_DRIVER_VRAM_FALLBACK": "1",
            "AIFILM_COMFY_SSH_TARGET": "user@private-node",
            "AIFILM_COMFY_SSH_KEY": "/tmp/private-key",
            "AIFILM_COMFY_SSH_KNOWN_HOSTS": "/tmp/known-hosts",
            "AIFILM_COMFY_SSH_HOSTKEY_ALIAS": "private-node",
            "AIFILM_COMFY_SSH_EXPECTED_HOSTNAME": "private-node",
        },
        clear=False,
    )
    @patch("comfy_video.subprocess.run")
    @patch("comfy_video._json_request")
    def test_submission_capacity_non_tunnel_skips_driver_probe_ssh(
        self, request: MagicMock, run: MagicMock
    ) -> None:
        """Non-loopback URL cannot use driver fallback SSH; Comfy metrics still admit."""
        request.side_effect = [
            {
                "system": {"ram_free": 16 * 1024**3},
                "devices": [
                    {
                        "name": "RTX 5090",
                        "type": "cuda",
                        "vram_total": 32 * 1024**3,
                        "vram_free": 28 * 1024**3,
                    }
                ],
            },
            {"queue_running": [], "queue_pending": []},
        ]
        report = submission_capacity("https://192.168.88.52:8188")
        self.assertTrue(report["ok"])
        self.assertEqual(report["observed"]["device"]["vram_source"], "comfyui")
        self.assertIn(
            "loopback SSH tunnel",
            str(report["observed"]["device"]["driver_vram_probe_error"] or ""),
        )
        run.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "AIFILM_COMFY_DRIVER_VRAM_FALLBACK": "1",
            "AIFILM_COMFY_SSH_TARGET": "user@private-node",
            "AIFILM_COMFY_SSH_KEY": "/tmp/private-key",
            "AIFILM_COMFY_SSH_KNOWN_HOSTS": "/tmp/known-hosts",
            "AIFILM_COMFY_SSH_HOSTKEY_ALIAS": "private-node",
            "AIFILM_COMFY_SSH_EXPECTED_HOSTNAME": "private-node",
        },
        clear=False,
    )
    @patch("comfy_video.subprocess.run")
    @patch("comfy_video._json_request")
    def test_submission_capacity_lookalike_ssh_skips_driver_uses_comfy(
        self, request: MagicMock, run: MagicMock
    ) -> None:
        """Lookalike tunnel identity fails driver probe; Comfy VRAM still admits."""
        request.side_effect = [
            {
                "system": {"ram_free": 16 * 1024**3},
                "devices": [
                    {
                        "name": "RTX 5090",
                        "type": "cuda",
                        "vram_total": 32 * 1024**3,
                        "vram_free": 28 * 1024**3,
                    }
                ],
            },
            {"queue_running": [], "queue_pending": []},
        ]
        run.side_effect = [
            MagicMock(returncode=0, stdout="123\n"),
            MagicMock(
                returncode=0,
                stdout=(
                    "ssh -fN -o HostKeyAlias=private-node-evil "
                    "-L 127.0.0.1:18188:127.0.0.1:8188 user@private-node-evil\n"
                ),
            ),
        ]
        report = submission_capacity("http://127.0.0.1:18188")
        self.assertTrue(report["ok"])
        self.assertEqual(report["observed"]["device"]["vram_source"], "comfyui")
        self.assertIn(
            "not the authenticated SSH tunnel",
            str(report["observed"]["device"]["driver_vram_probe_error"] or ""),
        )

    @patch("comfy_video._json_request")
    def test_submission_capacity_fails_closed_on_pressure_and_busy_queue(
        self, request: MagicMock
    ) -> None:
        request.side_effect = [
            {
                "system": {"ram_free": 2 * 1024**3},
                "devices": [{"name": "RTX 5090", "type": "cuda", "vram_free": 6 * 1024**3}],
            },
            {
                "queue_running": [[1, "existing", {"prompt": "PRIVATE"}]],
                "queue_pending": [],
            },
        ]
        report = submission_capacity("https://192.168.88.52:8188")
        self.assertFalse(report["ok"])
        self.assertEqual(
            {item["code"] for item in report["blockers"]},
            {"RAM_BELOW_FLOOR", "VRAM_BELOW_FLOOR", "COMFY_QUEUE_BUSY"},
        )
        self.assertNotIn("existing", str(report))
        self.assertNotIn("PRIVATE", str(report))

    @patch("comfy_video._json_request")
    def test_submission_capacity_rejects_cpu_memory_as_gpu_capacity(
        self, request: MagicMock
    ) -> None:
        request.side_effect = [
            {
                "system": {"ram_free": 16 * 1024**3},
                "devices": [
                    {"name": "RTX 5090", "type": "cuda", "vram_free": 6 * 1024**3},
                    {"name": "CPU", "type": "cpu", "vram_free": 128 * 1024**3},
                ],
            },
            {"queue_running": [], "queue_pending": []},
        ]
        report = submission_capacity("https://192.168.88.52:8188")
        self.assertFalse(report["ok"])
        self.assertEqual(
            {item["code"] for item in report["blockers"]},
            {"VRAM_BELOW_FLOOR"},
        )
        self.assertEqual(report["observed"]["device"]["name"], "RTX 5090")

    @patch("comfy_video._json_request")
    def test_submission_capacity_rejects_ambiguous_cuda_target(self, request: MagicMock) -> None:
        request.side_effect = [
            {
                "system": {"ram_free": 16 * 1024**3},
                "devices": [
                    {"name": "cuda:0", "type": "cuda", "vram_free": 28 * 1024**3},
                    {"name": "cuda:1", "type": "cuda"},
                ],
            },
            {"queue_running": [], "queue_pending": []},
        ]
        report = submission_capacity("https://192.168.88.52:8188")
        self.assertFalse(report["ok"])
        self.assertIsNone(report["observed"]["device"])
        self.assertIn("RESOURCE_METRICS_UNAVAILABLE", str(report["blockers"]))

    @patch("comfy_video._json_request")
    def test_submission_capacity_handles_malformed_system_without_raw_exception(
        self, request: MagicMock
    ) -> None:
        request.side_effect = [
            {"system": "invalid", "devices": "invalid"},
            {"queue_running": [], "queue_pending": []},
        ]
        report = submission_capacity("https://192.168.88.52:8188")
        self.assertFalse(report["ok"])
        self.assertEqual(
            {item["code"] for item in report["blockers"]},
            {"RESOURCE_METRICS_UNAVAILABLE"},
        )

    @patch("comfy_video._json_request")
    def test_submission_capacity_rejects_incomplete_or_malformed_queue(
        self, request: MagicMock
    ) -> None:
        for queue_payload in (
            {},
            {"queue_running": [], "queue_pending": [{"prompt_id": "busy"}]},
        ):
            with self.subTest(queue_payload=queue_payload):
                request.reset_mock()
                request.side_effect = [
                    {
                        "system": {"ram_free": 16 * 1024**3},
                        "devices": [
                            {
                                "name": "RTX 5090",
                                "type": "cuda",
                                "vram_free": 28 * 1024**3,
                            }
                        ],
                    },
                    queue_payload,
                ]
                with self.assertRaises(ComfyVideoError):
                    submission_capacity("https://192.168.88.52:8188")
                self.assertNotIn("/prompt", [call.args[1] for call in request.call_args_list])

    @patch("comfy_video._json_request")
    def test_submission_capacity_fails_closed_when_metrics_are_missing(
        self, request: MagicMock
    ) -> None:
        request.side_effect = [
            {"system": {}, "devices": []},
            {"queue_running": [], "queue_pending": []},
        ]
        with self.assertRaisesRegex(
            ComfyVideoError,
            "RESOURCE_METRICS_UNAVAILABLE",
        ):
            assert_submission_capacity("https://192.168.88.52:8188")

    @patch("comfy_video._json_request")
    def test_submit_uses_official_prompt_route_and_preserves_client_id(
        self, request: MagicMock
    ) -> None:
        request.side_effect = [
            {
                "system": {"ram_free": 16 * 1024**3},
                "devices": [{"name": "RTX 5090", "type": "cuda", "vram_free": 28 * 1024**3}],
            },
            {"queue_running": [], "queue_pending": []},
            {"prompt_id": "p-123"},
        ]
        graph = {"1": {"class_type": "KSampler", "inputs": {}}}
        prompt_id = submit(
            "https://192.168.88.52:8188",
            graph,
            client_id="client-123",
        )
        self.assertEqual(prompt_id, "p-123")
        args, kwargs = request.call_args_list[-1]
        self.assertEqual(args[1], "/prompt")
        self.assertEqual(kwargs["payload"]["client_id"], "client-123")

    @patch("comfy_video._json_request")
    def test_submit_never_posts_when_resource_tower_blocks(self, request: MagicMock) -> None:
        request.side_effect = [
            {
                "system": {"ram_free": 2 * 1024**3},
                "devices": [{"name": "RTX 5090", "type": "cuda", "vram_free": 6 * 1024**3}],
            },
            {"queue_running": [], "queue_pending": []},
        ]
        with self.assertRaisesRegex(
            ComfyVideoError,
            "RAM_BELOW_FLOOR.*VRAM_BELOW_FLOOR",
        ):
            submit(
                "https://192.168.88.52:8188",
                {"1": {"class_type": "KSampler", "inputs": {}}},
            )
        self.assertEqual(
            [call.args[1] for call in request.call_args_list],
            ["/system_stats", "/queue"],
        )

    @patch("comfy_video._wait_for_completion_ws")
    @patch("comfy_video._json_request")
    def test_wait_uses_websocket_then_reads_history(
        self,
        request: MagicMock,
        websocket_wait: MagicMock,
    ) -> None:
        request.side_effect = [
            {},
            {
                "p-1": {
                    "status": {"completed": True, "status_str": "success"},
                    "outputs": {
                        "9": {
                            "gifs": [
                                {
                                    "filename": "clip.mp4",
                                    "subfolder": "video",
                                    "type": "output",
                                }
                            ]
                        }
                    },
                }
            },
        ]
        result = wait_for_result(
            "https://192.168.88.52:8188",
            "p-1",
            client_id="client-1",
            timeout_sec=10,
            poll_sec=0,
        )
        websocket_wait.assert_called_once()
        self.assertEqual(result["filename"], "clip.mp4")

    @patch("comfy_video._wait_for_completion_ws")
    @patch("comfy_video._json_request")
    def test_wait_returns_completed_history_without_opening_websocket(
        self,
        request: MagicMock,
        websocket_wait: MagicMock,
    ) -> None:
        request.return_value = {
            "p-1": {
                "status": {"completed": True, "status_str": "success"},
                "outputs": {
                    "9": {
                        "images": [
                            {
                                "filename": "still.png",
                                "subfolder": "",
                                "type": "output",
                            }
                        ]
                    }
                },
            }
        }
        result = wait_for_result(
            "https://192.168.88.52:8188",
            "p-1",
            client_id="client-1",
            timeout_sec=10,
            poll_sec=0,
        )
        websocket_wait.assert_not_called()
        self.assertEqual(result["filename"], "still.png")

    @patch("comfy_video._json_request")
    def test_wait_fails_immediately_on_execution_error(self, request: MagicMock) -> None:
        request.return_value = {
            "p-1": {
                "status": {
                    "completed": False,
                    "status_str": "error",
                    "messages": [
                        [
                            "execution_error",
                            {
                                "node_id": "unet_high",
                                "exception_type": "RuntimeError",
                                "exception_message": "PRIVATE_PROMPT_MARKER",
                            },
                        ]
                    ],
                },
                "outputs": {},
            }
        }
        with self.assertRaisesRegex(
            ComfyVideoError,
            "unet_high.*RuntimeError",
        ):
            wait_for_result(
                "https://192.168.88.52:8188",
                "p-1",
                timeout_sec=10,
                poll_sec=0,
            )
        self.assertEqual(request.call_count, 1)

    @patch("comfy_video._json_request")
    @patch("websocket.create_connection")
    def test_websocket_timeout_history_fails_on_execution_error(
        self,
        create_connection: MagicMock,
        request: MagicMock,
    ) -> None:
        import websocket

        connection = MagicMock()
        connection.recv.side_effect = websocket.WebSocketTimeoutException()
        create_connection.return_value = connection
        request.return_value = {
            "p-1": {
                "status": {
                    "completed": False,
                    "status_str": "error",
                    "messages": [
                        [
                            "execution_error",
                            {
                                "node_id": "unet_high",
                                "exception_type": "RuntimeError",
                                "exception_message": "PRIVATE_PROMPT_MARKER",
                            },
                        ]
                    ],
                },
                "outputs": {},
            }
        }
        with self.assertRaisesRegex(
            ComfyVideoError,
            "unet_high.*RuntimeError",
        ):
            _wait_for_completion_ws(
                "https://192.168.88.52:8188",
                "p-1",
                client_id="client-1",
                timeout_sec=0.1,
            )
        self.assertEqual(create_connection.call_args.kwargs["redirect_limit"], 0)

    @patch("comfy_video._json_request")
    def test_submit_does_not_reflect_node_payload(self, request: MagicMock) -> None:
        request.side_effect = [
            {
                "system": {"ram_free": 16 * 1024**3},
                "devices": [{"name": "RTX 5090", "type": "cuda", "vram_free": 28 * 1024**3}],
            },
            {"queue_running": [], "queue_pending": []},
            {"error": "PRIVATE_PROMPT_MARKER"},
        ]
        with self.assertRaises(ComfyVideoError) as raised:
            submit("https://192.168.88.52:8188", {})
        self.assertNotIn("PRIVATE_PROMPT_MARKER", str(raised.exception))

    @patch("comfy_video._OPENER.open")
    def test_download_size_limit_preserves_existing_output(self, open_request: MagicMock) -> None:
        response = MagicMock()
        response.headers = {"Content-Length": str(513 * 1024 * 1024)}
        open_request.return_value.__enter__.return_value = response
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "approved.mp4"
            output.write_bytes(b"approved")
            with self.assertRaisesRegex(ComfyVideoError, "size limit"):
                download_result(
                    "https://192.168.88.52:8188",
                    {"filename": "artifact.mp4", "subfolder": "", "type": "output"},
                    output,
                )
            self.assertEqual(output.read_bytes(), b"approved")

    @patch("comfy_video._json_request")
    def test_cancel_prompt_refuses_non_atomic_global_interrupt(self, request: MagicMock) -> None:
        request.return_value = {
            "queue_running": [["n", "p-1"]],
            "queue_pending": [],
        }
        with self.assertRaisesRegex(ComfyVideoError, "not target-safe"):
            cancel_prompt("https://192.168.88.52:8188", "p-1")
        self.assertEqual(request.call_count, 1)

    @patch("comfy_video._json_request")
    def test_cancel_prompt_does_not_interrupt_someone_elses_job(self, request: MagicMock) -> None:
        request.return_value = {
            "queue_running": [["n", "other"]],
            "queue_pending": [],
        }
        with self.assertRaisesRegex(ComfyVideoError, "not present"):
            cancel_prompt("https://192.168.88.52:8188", "p-1")
        self.assertEqual(request.call_count, 1)

    @patch("comfy_video._json_request")
    def test_free_memory_is_explicit_and_uses_official_route(self, request: MagicMock) -> None:
        request.return_value = {}
        self.assertEqual(
            free_memory("https://192.168.88.52:8188"),
            {"ok": True, "action": "free_memory"},
        )
        self.assertEqual(request.call_args.args[1], "/free")
        self.assertEqual(
            request.call_args.kwargs["payload"],
            {"unload_models": True, "free_memory": True},
        )

    @patch("comfy_video._json_request")
    def test_queue_status_does_not_expose_prompt_payloads(self, request: MagicMock) -> None:
        request.return_value = {
            "queue_running": [[1, "run-1", {"secret": "prompt"}]],
            "queue_pending": [[2, "wait-1", {"secret": "prompt"}]],
        }
        self.assertEqual(
            queue_status("https://192.168.88.52:8188"),
            {
                "running": 1,
                "pending": 1,
                "running_prompt_ids": ["run-1"],
                "pending_prompt_ids": ["wait-1"],
            },
        )


if __name__ == "__main__":
    unittest.main()
