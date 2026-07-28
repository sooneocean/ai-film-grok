from __future__ import annotations

import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cli_comfy import _base_url  # noqa: E402
from comfy_armory import (  # noqa: E402
    ComfyArmoryError,
    compile_weapon_workflow,
    default_base_url,
    load_armory,
    probe_armory,
    select_weapon,
)


def test_armory_records_verified_private_node_without_credentials() -> None:
    armory = load_armory()
    assert armory["ok"] is True
    assert default_base_url(armory) == "http://192.168.88.52:8188"
    serialized = str(armory).lower()
    assert "private_key" not in serialized
    assert "password" not in serialized
    assert "token" not in serialized


@patch.dict("os.environ", {}, clear=True)
def test_comfy_cli_uses_verified_armory_node_without_env_configuration() -> None:
    assert _base_url(Namespace(base_url=None)) == "http://192.168.88.52:8188"


def test_max_quality_text_to_image_routes_to_verified_qwen_2512() -> None:
    route = select_weapon("text-to-image", quality="max_practical")
    assert route["ok"] is True
    assert route["weapon"]["id"] == "qwen-image-2512-quality"
    assert route["weapon"]["verified"]["real_pilot"] is True
    assert route["weapon"]["defaults"]["steps"] == 50


def test_identity_preserving_edit_routes_to_qwen_edit_2511() -> None:
    route = select_weapon("local-image-edit", identity_lock=True)
    assert route["ok"] is True
    assert route["weapon"]["id"] == "qwen-image-edit-2511-local"
    assert route["weapon"]["capabilities"]["identity_preserving_local_edit"] is True


def test_unavailable_layered_intent_fails_closed() -> None:
    with pytest.raises(ComfyArmoryError, match="no verified weapon"):
        select_weapon("layered-image")


def test_adult_meat_motion_auto_route_is_pilot_only() -> None:
    route = select_weapon(
        "adult-meat-motion-i2v",
        stage="pilot",
        allow_experimental=True,
    )
    assert route["weapon"]["id"] == "wan22-adult-meat-pilot"
    assert route["weapon"]["status"] == "experimental"
    assert route["weapon"]["capabilities"]["human_approval_required"] is True


def test_adult_meat_motion_pilot_requires_explicit_experimental_authorization() -> None:
    with pytest.raises(ComfyArmoryError, match="explicit experimental authorization"):
        select_weapon("adult-meat-motion-i2v", stage="pilot")


def test_adult_meat_motion_production_fails_closed() -> None:
    with pytest.raises(ComfyArmoryError, match="no promoted Wan 2.2 weapon"):
        select_weapon(
            "adult-meat-motion-i2v",
            stage="production",
            allow_experimental=True,
        )


def test_compile_qwen_2512_workflow_uses_route_defaults_and_safe_bindings() -> None:
    graph = compile_weapon_workflow(
        "qwen-image-2512-quality",
        prompt="A verified adult detective in a rainy Taipei alley.",
        seed=42,
        filename_prefix="aifilm/tests/qwen2512",
    )
    assert graph["positive"]["inputs"]["text"].startswith("A verified adult")
    assert graph["sampler"]["inputs"]["seed"] == 42
    assert graph["sampler"]["inputs"]["steps"] == 50
    assert graph["latent"]["inputs"]["width"] == 928
    assert graph["latent"]["inputs"]["height"] == 1664
    assert graph["unet"]["inputs"]["unet_name"] == "qwen_image_2512_fp8_e4m3fn.safetensors"
    assert graph["save"]["inputs"]["filename_prefix"] == "aifilm/tests/qwen2512"


def test_compile_edit_requires_uploaded_input_name() -> None:
    with pytest.raises(ComfyArmoryError, match="input image"):
        compile_weapon_workflow(
            "qwen-image-edit-2511-local",
            prompt="Change only the jacket color.",
            seed=7,
        )
    graph = compile_weapon_workflow(
        "qwen-image-edit-2511-local",
        prompt="Change only the jacket color.",
        seed=7,
        input_image_name="uploaded.png",
        filename_prefix="aifilm/tests/edit",
    )
    assert graph["load_image"]["inputs"]["image"] == "uploaded.png"
    assert graph["positive_encode"]["inputs"]["prompt"] == "Change only the jacket color."
    assert graph["sampler"]["inputs"]["seed"] == 7


@pytest.mark.parametrize("prompt,seed", [("", 7), ("valid", -1), ("valid", 2**64)])
def test_compile_rejects_empty_prompt_and_unsafe_seed(prompt: str, seed: int) -> None:
    with pytest.raises(ComfyArmoryError):
        compile_weapon_workflow(
            "qwen-image-2512-quality",
            prompt=prompt,
            seed=seed,
        )


@patch("comfy_armory._json_request")
def test_live_probe_marks_only_fully_installed_weapons_ready(request: MagicMock) -> None:
    model_lists = {
        "/models/diffusion_models": [
            "qwen_image_2512_fp8_e4m3fn.safetensors",
            "qwen_image_edit_2511_fp8mixed.safetensors",
        ],
        "/models/text_encoders": ["qwen_2.5_vl_7b_fp8_scaled.safetensors"],
        "/models/vae": ["qwen_image_vae.safetensors"],
        "/models/loras": ["Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"],
    }
    request.side_effect = lambda _url, route: model_lists[route]
    report = probe_armory("http://192.168.88.52:8188")
    assert report["ok"] is True
    assert {item["id"] for item in report["ready"]} == {
        "qwen-image-2512-quality",
        "qwen-image-edit-2511-local",
    }
    assert {item["id"] for item in report["blocked"]} == {
        "wan22-i2v-quality",
        "wan22-adult-intimacy-baseline",
        "wan22-adult-meat-pilot",
    }
