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
    assert default_base_url(armory) == "http://127.0.0.1:18188"
    serialized = str(armory).lower()
    assert "private_key" not in serialized
    assert "password" not in serialized
    assert "token" not in serialized


@patch.dict(
    "os.environ",
    {"AIFILM_COMFYUI_BASE_URL": "http://192.168.88.52:8188"},
)
def test_explicit_armory_ignores_inherited_environment_override() -> None:
    assert default_base_url(load_armory()) == "http://127.0.0.1:18188"


@patch.dict("os.environ", {}, clear=True)
def test_comfy_cli_uses_verified_armory_node_without_env_configuration() -> None:
    assert _base_url(Namespace(base_url=None)) == "http://127.0.0.1:18188"


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


def test_unverified_high_priority_candidate_cannot_enter_armory() -> None:
    forged = load_armory()
    forged["weapons"].insert(
        0,
        {
            "id": "forged",
            "status": "unverified",
            "priority": 999,
            "intents": ["text-to-image"],
            "quality_tiers": ["max_practical"],
            "verified": {"real_pilot": False},
        },
    )
    with patch("comfy_armory.load_armory", return_value=forged):
        route = select_weapon("text-to-image")
    assert route["weapon"]["id"] == "qwen-image-2512-quality"


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


@pytest.mark.parametrize(
    "filename_prefix,input_name",
    [
        ("../../escape", None),
        ("/absolute", None),
        ("safe/output", "../../secret.png"),
        ("safe/output", "/etc/passwd"),
    ],
)
def test_compile_rejects_unsafe_relative_media_paths(
    filename_prefix: str,
    input_name: str | None,
) -> None:
    weapon = "qwen-image-edit-2511-local" if input_name is not None else "qwen-image-2512-quality"
    with pytest.raises(ComfyArmoryError, match="safe relative"):
        compile_weapon_workflow(
            weapon,
            prompt="safe prompt",
            seed=7,
            filename_prefix=filename_prefix,
            input_image_name=input_name,
        )


@patch("comfy_armory._json_request")
def test_live_probe_marks_only_fully_installed_weapons_ready(
    request: MagicMock,
) -> None:
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
    report = probe_armory("https://192.168.88.52:8188")
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


@patch("comfy_armory._model_sha256")
@patch("comfy_armory._json_request")
def test_live_probe_blocks_only_weapon_with_unreadable_required_hash(
    request: MagicMock,
    model_sha256: MagicMock,
) -> None:
    armory = load_armory()
    installed = {
        group: sorted(
            {
                name
                for weapon in armory["weapons"]
                for name in weapon.get("requirements", {}).get(group, [])
            }
        )
        for group in ("diffusion_models", "text_encoders", "vae", "loras")
    }
    request.side_effect = lambda _url, route: installed[route.removeprefix("/models/")]
    model_sha256.side_effect = ComfyArmoryError("metadata unavailable")

    report = probe_armory("https://192.168.88.52:8188")

    assert "wan22-i2v-quality" in report["ready_ids"]
    assert "qwen-image-2512-quality" in report["ready_ids"]
    assert {item["id"] for item in report["blocked"]} == {"wan22-adult-meat-pilot"}
    assert report["blocked"][0]["sha256_errors"]["loras"]


@patch("comfy_armory._model_sha256", return_value="0" * 64)
@patch("comfy_armory._json_request")
def test_live_probe_blocks_same_name_adult_lora_with_wrong_hash(
    request: MagicMock,
    _sha256: MagicMock,
) -> None:
    request.side_effect = lambda _url, route: {
        "/models/diffusion_models": [
            "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
            "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
        ],
        "/models/text_encoders": ["umt5_xxl_fp8_e4m3fn_scaled.safetensors"],
        "/models/vae": ["wan_2.1_vae.safetensors"],
        "/models/loras": ["NSFW-22-H-e8.safetensors", "NSFW-22-L-e8.safetensors"],
    }[route]
    report = probe_armory("https://192.168.88.52:8188")
    blocked = {item["id"]: item for item in report["blocked"]}
    assert "wan22-adult-meat-pilot" in blocked
    assert blocked["wan22-adult-meat-pilot"]["sha256_mismatches"]


@patch("comfy_armory._json_request")
def test_live_probe_accepts_exact_adult_lora_hashes(request: MagicMock) -> None:
    request.side_effect = lambda _url, route: {
        "/models/diffusion_models": [
            "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
            "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
        ],
        "/models/text_encoders": ["umt5_xxl_fp8_e4m3fn_scaled.safetensors"],
        "/models/vae": ["wan_2.1_vae.safetensors"],
        "/models/loras": ["NSFW-22-H-e8.safetensors", "NSFW-22-L-e8.safetensors"],
    }[route]
    hashes = {
        "NSFW-22-H-e8.safetensors": "34e2144d3cd65360f97d09ccbe03e1c39a096df6c9234af5fe3899d1b63cda39",
        "NSFW-22-L-e8.safetensors": "d6b783742f4d5fd63a0223ae1d5bf64fc995a6b408480ac2a00528ae0d4146db",
    }
    with patch(
        "comfy_armory._model_sha256",
        side_effect=lambda _url, _group, filename: hashes[filename],
    ):
        report = probe_armory("https://192.168.88.52:8188")
    assert "wan22-adult-meat-pilot" in report["ready_ids"]
