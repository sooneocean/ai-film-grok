from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cli_node import node_status, run_node  # noqa: E402
from comfy_recovery import ComfyRecoveryConfig  # noqa: E402


def test_status_marks_unreachable_comfy_as_unavailable_without_raw_error() -> None:
    with (
        patch("cli_node.inventory", side_effect=RuntimeError("connection refused token=secret")),
        patch(
            "cli_node._audio_status",
            return_value={"status": "unavailable", "reason": "not_configured"},
        ),
    ):
        report = node_status("http://192.168.88.52:8188")
    assert report["status"] == "unavailable"
    assert report["comfy"]["status"] == "unavailable"
    assert "secret" not in json.dumps(report)


def test_status_marks_live_queue_as_busy() -> None:
    live = {
        "system": {"comfyui_version": "x"},
        "devices": [{"type": "cuda", "vram_total": 32, "vram_free": 20}],
        "model_counts": {"diffusion_models": 2},
        "queue": {"running": 1, "pending": 0},
    }
    armory = {"ready": [{"id": "wan"}], "blocked": [], "ready_ids": ["wan"]}
    with (
        patch("cli_node.inventory", return_value=live),
        patch("cli_node.probe_armory", return_value=armory),
        patch(
            "cli_node._audio_status", return_value={"status": "reachable", "models": {"tts": True}}
        ),
    ):
        report = node_status("http://192.168.88.52:8188")
    assert report["status"] == "busy"
    assert report["comfy"]["queue"] == {"running": 1, "pending": 0}


def test_run_node_loads_local_config_before_reading_audio_status() -> None:
    args = Namespace(node_action="status", base_url="http://127.0.0.1:18188", receipt=None)
    with (
        patch("config_loader.get_config") as get_config,
        patch("cli_node.node_status", return_value={"status": "reachable"}),
    ):
        assert run_node(args, emit=lambda _payload: None) == 0
    get_config.assert_called_once_with()


def test_recover_requires_confirmation_before_any_remote_operation(capsys) -> None:
    args = Namespace(
        node_action="recover", base_url="http://127.0.0.1:18188", confirm=False, receipt=None
    )
    with patch("cli_node._recover") as recover:
        assert run_node(args, emit=lambda payload: print(json.dumps(payload))) == 2
    recover.assert_not_called()
    assert "--confirm" in capsys.readouterr().out


def test_recover_rejects_queue_check_on_a_different_endpoint() -> None:
    args = Namespace(
        node_action="recover", base_url="http://192.168.88.52:8188", confirm=True, receipt=None
    )
    config = ComfyRecoveryConfig(
        "user@192.168.88.52", Path("/key"), 18188, 8188, r"C:\\ComfyUI_windows_portable"
    )
    with (
        patch("comfy_recovery.config_from_env", return_value=config),
        patch("comfy_recovery.validate_recovery_config", return_value=config),
        patch("cli_node.queue_status") as queue,
    ):
        assert run_node(args, emit=lambda _payload: None) == 2
    queue.assert_not_called()
