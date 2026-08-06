from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from comfy_armory import load_armory  # noqa: E402
from seedvr2_probe import REQUIRED_CLASS_TYPES, probe_seedvr2  # noqa: E402


def _object_info(*, include_all: bool = True) -> dict[str, object]:
    classes = {class_type: {"display_name": class_type} for class_type in REQUIRED_CLASS_TYPES}
    classes["SeedVR2LoadDiTModel"] = {
        "display_name": "SeedVR2 Load DiT Model",
        "input": {
            "required": {
                "model": [
                    "COMBO",
                    {
                        "default": "seedvr2_ema_3b_fp8_e4m3fn.safetensors",
                        "options": [
                            "seedvr2_ema_3b_fp8_e4m3fn.safetensors",
                            "seedvr2_ema_7b_fp16.safetensors",
                        ],
                    },
                ]
            }
        },
        "python_module": "custom_nodes.ComfyUI-SeedVR2_VideoUpscaler",
    }
    if not include_all:
        classes.pop("SeedVR2VideoUpscaler")
    return classes


@patch("seedvr2_probe._json_request")
def test_probe_proves_nodes_but_never_claims_weights_or_execution_ready(
    request: MagicMock,
) -> None:
    request.return_value = _object_info()

    report = probe_seedvr2("http://127.0.0.1:18188")

    request.assert_called_once_with("http://127.0.0.1:18188", "/object_info")
    assert report["ok"] is True
    assert report["custom_nodes_ready"] is True
    assert report["weights_state"] == "unverified"
    assert report["execution_ready"] is False
    assert report["auto_download_blocked"] is True
    assert report["model_candidates"] == [
        "seedvr2_ema_3b_fp8_e4m3fn.safetensors",
        "seedvr2_ema_7b_fp16.safetensors",
    ]


@patch("seedvr2_probe._json_request")
def test_probe_fails_closed_when_a_required_class_type_is_missing(
    request: MagicMock,
) -> None:
    request.return_value = _object_info(include_all=False)

    report = probe_seedvr2("http://127.0.0.1:18188")

    assert report["ok"] is True
    assert report["custom_nodes_ready"] is False
    assert report["missing_class_types"] == ["SeedVR2VideoUpscaler"]
    assert report["execution_ready"] is False


@patch("seedvr2_probe._json_request")
def test_probe_fails_closed_when_loader_model_contract_is_malformed(
    request: MagicMock,
) -> None:
    object_info = _object_info()
    object_info["SeedVR2LoadDiTModel"]["input"]["required"]["model"] = "unexpected"
    request.return_value = object_info

    report = probe_seedvr2("http://127.0.0.1:18188")

    assert report["custom_nodes_ready"] is True
    assert report["model_contract_ready"] is False
    assert report["model_candidates"] == []
    assert report["execution_ready"] is False


def test_registry_keeps_seedvr2_research_only_and_blocks_automatic_actions() -> None:
    armory = load_armory()
    weapon = next(
        item
        for item in armory["research_weapons"]
        if item["id"] == "seedvr2-video-restoration-research"
    )

    assert weapon["readiness"] == "custom_nodes_ready_weights_unverified"
    assert weapon["allowed_stages"] == ["research"]
    assert {
        "no_auto_download",
        "no_auto_execute",
        "no_auto_promotion",
        "not_final",
    }.issubset(weapon["restrictions"])
    assert set(weapon["required_class_types"]) == set(REQUIRED_CLASS_TYPES)
    assert weapon["probe_command"] == "./scripts/runtime-python scripts/seedvr2_probe.py"
