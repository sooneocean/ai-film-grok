from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from comfy_video import (  # noqa: E402
    WAN22_ADULT_PROFILE,
    WAN22_OFFICIAL_PROFILE,
    ComfyVideoError,
    _json_request,
    _wait_for_completion_ws,
    apply_workflow_overrides,
    assert_local_only_workflow,
    build_wan22_i2v_prompt,
    cancel_prompt,
    free_memory,
    inventory,
    load_api_workflow,
    normalize_base_url,
    queue_status,
    submit,
    upload_image,
    validate_adult_request,
    wait_for_result,
    workflow_sha256,
)


class ComfyVideoTests(unittest.TestCase):
    @patch("comfy_video._OPENER.open")
    def test_json_request_accepts_empty_success_body(self, open_request: MagicMock) -> None:
        response = MagicMock()
        response.read.return_value = b""
        open_request.return_value.__enter__.return_value = response
        self.assertEqual(
            _json_request(
                "http://192.168.88.52:8188",
                "/free",
                method="POST",
                payload={"free_memory": True},
            ),
            {},
        )

    def test_private_comfyui_url_is_accepted(self) -> None:
        self.assertEqual(
            normalize_base_url("http://192.168.88.52:8188/"),
            "http://192.168.88.52:8188",
        )
        self.assertEqual(normalize_base_url("http://127.0.0.1:8188"), "http://127.0.0.1:8188")
        self.assertEqual(normalize_base_url("http://[fd00::1]:8188"), "http://[fd00::1]:8188")

    def test_public_or_credentialed_url_is_rejected(self) -> None:
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("https://example.com")
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("http://user:pass@192.168.88.52:8188")
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("http://0.0.0.0:8188")
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("http://169.254.169.254:8188")
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("http://192.0.0.1:8188")
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("http://[fe80::1]:8188")
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("http://192.168.88.52:8188?token=secret")
        with self.assertRaises(ComfyVideoError):
            normalize_base_url("http://192.168.88.52:8188/#fragment")

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
                upload_image("http://192.168.88.52:8188", image)

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
            assert_local_only_workflow("http://192.168.88.52:8188", graph)

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
            assert_local_only_workflow("http://192.168.88.52:8188", graph)

    @patch("comfy_video._json_request")
    def test_local_only_validation_rejects_unknown_or_custom_nodes(
        self,
        request: MagicMock,
    ) -> None:
        graph = {"1": {"class_type": "OpenAIImageNode", "inputs": {}}}
        request.return_value = {}
        with self.assertRaisesRegex(ComfyVideoError, "metadata unavailable"):
            assert_local_only_workflow("http://192.168.88.52:8188", graph)

        request.return_value = {
            "OpenAIImageNode": {
                "category": "image/generate",
                "python_module": "custom_nodes.openai",
            }
        }
        with self.assertRaisesRegex(ComfyVideoError, "external API node"):
            assert_local_only_workflow("http://192.168.88.52:8188", graph)

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
            "http://192.168.88.52:8188",
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
        report = inventory("http://192.168.88.52:8188")
        self.assertEqual(report["model_counts"]["diffusion_models"], 2)
        self.assertEqual(report["queue"]["pending"], 1)
        self.assertNotIn("object_info", report)

    @patch("comfy_video._json_request")
    def test_submit_uses_official_prompt_route_and_preserves_client_id(
        self, request: MagicMock
    ) -> None:
        request.return_value = {"prompt_id": "p-123"}
        graph = {"1": {"class_type": "KSampler", "inputs": {}}}
        prompt_id = submit(
            "http://192.168.88.52:8188",
            graph,
            client_id="client-123",
        )
        self.assertEqual(prompt_id, "p-123")
        args, kwargs = request.call_args
        self.assertEqual(args[1], "/prompt")
        self.assertEqual(kwargs["payload"]["client_id"], "client-123")

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
            "http://192.168.88.52:8188",
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
            "http://192.168.88.52:8188",
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
                                "exception_message": "invalid tensor shape",
                            },
                        ]
                    ],
                },
                "outputs": {},
            }
        }
        with self.assertRaisesRegex(
            ComfyVideoError,
            "unet_high.*invalid tensor shape",
        ):
            wait_for_result(
                "http://192.168.88.52:8188",
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
                                "exception_message": "invalid tensor shape",
                            },
                        ]
                    ],
                },
                "outputs": {},
            }
        }
        with self.assertRaisesRegex(
            ComfyVideoError,
            "unet_high.*invalid tensor shape",
        ):
            _wait_for_completion_ws(
                "http://192.168.88.52:8188",
                "p-1",
                client_id="client-1",
                timeout_sec=0.1,
            )
        self.assertEqual(create_connection.call_args.kwargs["redirect_limit"], 0)

    @patch("comfy_video._json_request")
    def test_cancel_prompt_refuses_non_atomic_global_interrupt(self, request: MagicMock) -> None:
        request.return_value = {
            "queue_running": [["n", "p-1"]],
            "queue_pending": [],
        }
        with self.assertRaisesRegex(ComfyVideoError, "not target-safe"):
            cancel_prompt("http://192.168.88.52:8188", "p-1")
        self.assertEqual(request.call_count, 1)

    @patch("comfy_video._json_request")
    def test_cancel_prompt_does_not_interrupt_someone_elses_job(self, request: MagicMock) -> None:
        request.return_value = {
            "queue_running": [["n", "other"]],
            "queue_pending": [],
        }
        with self.assertRaisesRegex(ComfyVideoError, "not present"):
            cancel_prompt("http://192.168.88.52:8188", "p-1")
        self.assertEqual(request.call_count, 1)

    @patch("comfy_video._json_request")
    def test_free_memory_is_explicit_and_uses_official_route(self, request: MagicMock) -> None:
        request.return_value = {}
        self.assertEqual(
            free_memory("http://192.168.88.52:8188"),
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
            queue_status("http://192.168.88.52:8188"),
            {
                "running": 1,
                "pending": 1,
                "running_prompt_ids": ["run-1"],
                "pending_prompt_ids": ["wait-1"],
            },
        )


if __name__ == "__main__":
    unittest.main()
