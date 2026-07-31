from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cli_comfy import _base_url, run_comfy  # noqa: E402
from comfy_armory import (  # noqa: E402
    ComfyArmoryError,
    assert_registered_weapon_workflow,
    compile_weapon_workflow,
    default_base_url,
    identify_registered_weapon_workflow,
    load_armory,
    probe_armory,
    select_weapon,
)
from comfy_video import workflow_sha256  # noqa: E402


def test_armory_records_verified_private_node_without_credentials() -> None:
    armory = load_armory()
    assert armory["ok"] is True
    assert default_base_url(armory) == "http://127.0.0.1:18188"
    serialized = str(armory).lower()
    assert "private_key" not in serialized
    assert "password" not in serialized
    assert "token" not in serialized


def test_audio_research_weapons_bind_versioned_evidence() -> None:
    armory = load_armory()
    root = Path(__file__).resolve().parents[1]
    research = {
        weapon["id"]: weapon
        for weapon in armory["research_weapons"]
        if weapon["id"] in {"mmaudio-video-foley-pilot", "vibevoice-asr-review-5090"}
    }

    assert set(research) == {"mmaudio-video-foley-pilot", "vibevoice-asr-review-5090"}
    for weapon_id, weapon in research.items():
        relative = Path(weapon["latest_canary_receipt_path"])
        assert relative.parts[:2] == ("registry", "evidence")
        evidence = json.loads((root / relative).read_text(encoding="utf-8"))
        assert evidence["weapon_id"] == weapon_id
        assert evidence["production_eligible"] is False


def test_pilot_template_hashes_are_registry_bound() -> None:
    armory = load_armory()
    by_id = {weapon["id"]: weapon for weapon in armory["weapons"]}
    root = Path(__file__).resolve().parents[1]
    for weapon_id in (
        "infinite-talk-stable-pilot",
        "fantasy-talking-6step-pilot",
        "hunyuan15-720p-i2v-sr-pilot",
        "ace-step15-xl-rnb-pilot",
        "ltx23-native-i2v-pilot",
        "ltx23-distilled-fp8-fast-broll-pilot",
    ):
        weapon = by_id[weapon_id]
        graph = json.loads((root / weapon["workflow_template"]).read_text(encoding="utf-8"))
        assert workflow_sha256(graph) == weapon["verified"]["workflow_template_sha256"]


def test_infinite_talk_frame_defaults_match_the_pilot_workflow() -> None:
    armory = load_armory()
    weapon = next(item for item in armory["weapons"] if item["id"] == "infinite-talk-stable-pilot")
    root = Path(__file__).resolve().parents[1]
    graph = json.loads((root / weapon["workflow_template"]).read_text(encoding="utf-8"))

    assert graph["4"]["inputs"]["num_frames"] == weapon["defaults"]["num_frames"]
    assert graph["4"]["inputs"]["fps"] == weapon["defaults"]["fps"]


def test_wan_quality_template_decodes_the_completed_low_noise_pass() -> None:
    root = Path(__file__).resolve().parents[1]
    graph = json.loads(
        (root / "templates/comfy/wan22-i2v-quality-api.json").read_text(encoding="utf-8")
    )

    assert graph["ks_h"]["inputs"]["latent_image"] == ["i2v", 2]
    assert graph["ks_l"]["inputs"]["latent_image"] == ["ks_h", 0]
    assert graph["decode"]["inputs"]["samples"] == ["ks_l", 0]


def test_wan_portrait_pilot_preserves_a_portrait_latent_canvas() -> None:
    root = Path(__file__).resolve().parents[1]
    graph = json.loads(
        (root / "templates/comfy/wan22-i2v-portrait-pilot-api.json").read_text(encoding="utf-8")
    )
    weapon = next(
        item for item in load_armory()["weapons"] if item["id"] == "wan22-i2v-portrait-pilot"
    )

    assert graph["i2v"]["inputs"]["width"] == weapon["defaults"]["width"] == 576
    assert graph["i2v"]["inputs"]["height"] == weapon["defaults"]["height"] == 1024
    assert graph["i2v"]["inputs"]["height"] > graph["i2v"]["inputs"]["width"]
    assert workflow_sha256(graph) == weapon["verified"]["workflow_template_sha256"]
    assert weapon["requirements"]["clip_vision"] == ["clip_vision_h.safetensors"]
    assert weapon["requirements"]["loras"] == [
        "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors",
        "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors",
    ]


@patch("comfy_armory._json_request")
def test_portrait_wan_probe_fails_closed_when_template_lora_is_missing(
    request: MagicMock,
) -> None:
    request.side_effect = lambda _url, route: {
        "/models/checkpoints": [],
        "/models/diffusion_models": [
            "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
            "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
        ],
        "/models/text_encoders": ["umt5_xxl_fp8_e4m3fn_scaled.safetensors"],
        "/models/vae": ["wan_2.1_vae.safetensors"],
        "/models/clip_vision": ["clip_vision_h.safetensors"],
        "/models/loras": ["wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors"],
        "/models/latent_upscale_models": [],
    }[route]

    report = probe_armory("https://192.168.88.52:8188")
    blocked = {item["id"]: item for item in report["blocked"]}

    assert "wan22-i2v-portrait-pilot" in blocked
    assert blocked["wan22-i2v-portrait-pilot"]["missing"] == {
        "loras": ["wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors"]
    }


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


def test_explicit_experimental_pilot_can_compile_its_first_canary() -> None:
    route = select_weapon(
        "image-to-video",
        quality="max_practical",
        stage="pilot",
        allow_experimental=True,
    )

    assert route["weapon"]["id"] == "wan22-i2v-portrait-pilot"
    assert route["weapon"]["verified"]["real_pilot"] is False


def test_unattested_experimental_weapon_cannot_route_without_pilot_opt_in() -> None:
    route = select_weapon("image-to-video", quality="max_practical", stage="pilot")

    assert route["weapon"]["id"] == "wan22-i2v-quality"


def test_experimental_weapon_cannot_route_in_production() -> None:
    with pytest.raises(ComfyArmoryError, match="no verified weapon"):
        select_weapon(
            "short-shot-i2v-sr-pilot",
            quality="max_practical",
            stage="production",
            allow_experimental=True,
        )


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


@pytest.mark.parametrize(
    ("intent", "weapon_id"),
    [
        ("talking-avatar-stable-pilot", "infinite-talk-stable-pilot"),
        ("talking-avatar-expressive-pilot", "fantasy-talking-6step-pilot"),
    ],
)
def test_talking_avatar_routes_are_explicit_pilot_only(
    intent: str,
    weapon_id: str,
) -> None:
    route = select_weapon(
        intent,
        stage="pilot",
        allow_experimental=True,
    )
    assert route["weapon"]["id"] == weapon_id
    assert route["weapon"]["status"] == "experimental"
    assert route["weapon"]["capabilities"]["pilot_only"] is True
    assert route["weapon"]["capabilities"]["human_approval_required"] is True
    with pytest.raises(ComfyArmoryError, match="pilot"):
        select_weapon(
            intent,
            stage="production",
            allow_experimental=True,
        )


def test_talking_avatar_pilot_requires_explicit_experimental_authorization() -> None:
    with pytest.raises(ComfyArmoryError, match="experimental authorization"):
        select_weapon("talking-avatar-stable-pilot", stage="pilot")


def test_run_workflow_cannot_bypass_experimental_gate_by_omitting_weapon_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    weapon = next(
        item for item in load_armory()["weapons"] if item["id"] == "infinite-talk-stable-pilot"
    )
    workflow = Path(__file__).resolve().parents[1] / weapon["workflow_template"]
    args = Namespace(
        base_url="http://127.0.0.1:18188",
        comfy_action="run-workflow",
        workflow=workflow,
        overrides=None,
        timeout=1,
        allow_external_api_nodes=False,
        weapon_id=None,
        production_stage="production",
        allow_experimental=False,
        receipt=None,
    )
    with patch("cli_comfy.submit") as submit:
        assert run_comfy(args) == 2
    submit.assert_not_called()
    report = json.loads(capsys.readouterr().out)
    assert "pilot-only" in report["error"]


def test_modified_experimental_workflow_cannot_escape_through_generic_bypass(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    weapon = next(
        item for item in load_armory()["weapons"] if item["id"] == "infinite-talk-stable-pilot"
    )
    template = Path(__file__).resolve().parents[1] / weapon["workflow_template"]
    graph = json.loads(template.read_text(encoding="utf-8"))
    graph["4"]["inputs"]["audio_scale"] = 4.0
    workflow = tmp_path / "tampered.json"
    workflow.write_text(json.dumps(graph), encoding="utf-8")
    args = Namespace(
        base_url="http://127.0.0.1:18188",
        comfy_action="run-workflow",
        workflow=workflow,
        overrides=None,
        timeout=1,
        allow_external_api_nodes=True,
        weapon_id=None,
        production_stage="pilot",
        allow_experimental=True,
        receipt=None,
    )
    with patch("cli_comfy.submit") as submit:
        assert run_comfy(args) == 2
    submit.assert_not_called()
    report = json.loads(capsys.readouterr().out)
    assert "--weapon-id required" in report["error"]


@pytest.mark.parametrize(
    "class_type",
    (
        "HunyuanVideo15ImageToVideo",
        "LTXAVTextEncoderLoader",
        "ModelSamplingLTXV",
        "TextEncodeAceStepAudio1.5",
    ),
)
def test_registered_experimental_model_family_requires_explicit_weapon_id(
    class_type: str,
) -> None:
    graph = {"attacker": {"class_type": class_type, "inputs": {}}}

    with pytest.raises(ComfyArmoryError, match="--weapon-id required"):
        identify_registered_weapon_workflow(graph)


def test_generic_hunyuan_workflow_is_blocked_before_submission(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow = tmp_path / "hunyuan.json"
    workflow.write_text(
        json.dumps(
            {
                "pilot": {
                    "class_type": "HunyuanVideo15ImageToVideo",
                    "inputs": {},
                }
            }
        ),
        encoding="utf-8",
    )
    args = Namespace(
        base_url="http://127.0.0.1:18188",
        comfy_action="run-workflow",
        workflow=workflow,
        overrides=None,
        timeout=1,
        allow_external_api_nodes=False,
        weapon_id=None,
        production_stage="production",
        allow_experimental=False,
        receipt=None,
    )

    with patch("cli_comfy.submit") as submit:
        assert run_comfy(args) == 2
    submit.assert_not_called()
    report = json.loads(capsys.readouterr().out)
    assert "--weapon-id required" in report["error"]


def test_unregistered_core_only_workflow_remains_generic() -> None:
    graph = {
        "sampler": {
            "class_type": "KSampler",
            "inputs": {},
        }
    }

    assert identify_registered_weapon_workflow(graph) is None


def test_compile_hunyuan15_sr_pilot_binds_only_reviewable_slots() -> None:
    graph = compile_weapon_workflow(
        "hunyuan15-720p-i2v-sr-pilot",
        prompt="The armored knight slowly turns toward the camera.",
        seed=2026073002,
        input_image_name="approved/knight.png",
        filename_prefix="aifilm/evaluation/hunyuan15-sr",
    )

    assert graph["source"]["inputs"]["image"] == "approved/knight.png"
    assert graph["positive"]["inputs"]["text"].startswith("The armored knight")
    assert graph["noise"]["inputs"]["noise_seed"] == 2026073002
    assert graph["scheduler"]["inputs"]["steps"] == 20
    assert graph["sr_scheduler"]["inputs"]["steps"] == 8
    assert graph["sr_unet"]["inputs"]["unet_name"].endswith(
        "1080p_sr_distilled_fp8_scaled.safetensors"
    )
    assert graph["sr_upscale"]["inputs"]["width"] == 1920
    assert graph["sr_upscale"]["inputs"]["height"] == 1080
    assert graph["save"]["inputs"]["filename_prefix"] == "aifilm/evaluation/hunyuan15-sr"


def test_compile_ace_step15_rnb_pilot_binds_prompt_seed_and_duration() -> None:
    graph = compile_weapon_workflow(
        "ace-step15-xl-rnb-pilot",
        prompt="Instrumental sensual R&B, warm Rhodes, restrained bass, no vocals.",
        seed=2026073003,
        filename_prefix="aifilm/evaluation/ace15-rnb",
    )

    assert graph["conditioning"]["inputs"]["tags"].startswith("Instrumental sensual R&B")
    assert graph["conditioning"]["inputs"]["lyrics"] == "[Instrumental]"
    assert graph["conditioning"]["inputs"]["duration"] == 15.0
    assert graph["latent"]["inputs"]["seconds"] == 15.0
    assert graph["sampler"]["inputs"]["seed"] == 2026073003
    assert graph["sampler"]["inputs"]["steps"] == 8
    assert graph["save"]["inputs"]["filename_prefix"] == "aifilm/evaluation/ace15-rnb"


def test_compile_ltx23_native_pilot_binds_image_prompt_and_seed() -> None:
    graph = compile_weapon_workflow(
        "ltx23-native-i2v-pilot",
        prompt="The knight turns slowly; ambient room tone, no speech.",
        seed=2026073004,
        input_image_name="approved/knight.png",
        filename_prefix="aifilm/evaluation/ltx23-native",
    )

    assert graph["source"]["inputs"]["image"] == "approved/knight.png"
    assert graph["303"]["inputs"]["text"].startswith("The knight turns slowly")
    assert graph["277"]["inputs"]["noise_seed"] == 2026073004
    assert graph["310"]["inputs"]["fps"] == 25
    assert graph["save"]["inputs"]["filename_prefix"] == "aifilm/evaluation/ltx23-native"


def test_registered_ltx23_pilot_allows_only_declared_audio_conditioning_extension() -> None:
    graph = compile_weapon_workflow(
        "ltx23-native-i2v-pilot",
        prompt="An adult woman speaks naturally with subtle movement.",
        seed=2026073104,
        input_image_name="approved/state.png",
        filename_prefix="aifilm/pilot/ltx23-dialogue",
    )
    graph["audio_source"] = {"class_type": "LoadAudio", "inputs": {"audio": "approved/line-ja.mp3"}}
    graph["audio_encode"] = {
        "class_type": "LTXVAudioVAEEncode",
        "inputs": {"audio": ["audio_source", 0], "audio_vae": ["279", 0]},
    }
    graph["318"]["inputs"]["audio_latent"] = ["audio_encode", 0]

    def node_info(_base_url: str, route: str) -> dict[str, dict[str, object]]:
        class_type = route.rsplit("/", 1)[-1]
        return {class_type: {"python_module": "nodes", "category": "local", "api_node": False}}

    with patch("comfy_armory._json_request", side_effect=node_info):
        assert_registered_weapon_workflow("http://127.0.0.1:18188", "ltx23-native-i2v-pilot", graph)

    graph["audio_encode"]["inputs"]["audio_vae"] = ["316", 2]
    with pytest.raises(ComfyArmoryError, match="audio-conditioning"):
        assert_registered_weapon_workflow("http://127.0.0.1:18188", "ltx23-native-i2v-pilot", graph)


def test_compile_ltx23_distilled_fp8_broll_pilot_binds_an_empty_scene_contract() -> None:
    graph = compile_weapon_workflow(
        "ltx23-distilled-fp8-fast-broll-pilot",
        prompt="An empty rain-soaked alley; ambient rain only, no people or speech.",
        seed=2026073101,
        input_image_name="approved/empty-alley.png",
        filename_prefix="aifilm/evaluation/ltx23-distilled-fp8",
    )

    assert graph["316"]["inputs"]["ckpt_name"] == "ltx-2.3-22b-distilled-fp8.safetensors"
    assert graph["source"]["inputs"]["image"] == "approved/empty-alley.png"
    assert graph["303"]["inputs"]["text"].startswith("An empty rain-soaked alley")
    assert graph["277"]["inputs"]["noise_seed"] == 2026073101
    assert graph["save"]["inputs"]["filename_prefix"] == "aifilm/evaluation/ltx23-distilled-fp8"


@pytest.mark.parametrize(
    "prompt",
    [
        "Two people have a dialogue in a continuous dramatic scene.",
        "A character speaks to camera with narration.",
    ],
)
def test_compile_ltx23_distilled_fp8_broll_rejects_dialogue_and_character_prompting(
    prompt: str,
) -> None:
    with pytest.raises(ComfyArmoryError, match="declared pilot contract"):
        compile_weapon_workflow(
            "ltx23-distilled-fp8-fast-broll-pilot",
            prompt=prompt,
            seed=1,
            input_image_name="approved/empty-alley.png",
        )


def test_compile_infinite_talk_binds_image_audio_prompt_seed_and_stable_scale() -> None:
    weapon = next(
        item for item in load_armory()["weapons"] if item["id"] == "infinite-talk-stable-pilot"
    )
    graph = compile_weapon_workflow(
        "infinite-talk-stable-pilot",
        prompt="The adult character speaks calmly with restrained head motion.",
        seed=20260729,
        input_image_name="approved/hero.png",
        input_audio_name="approved/hero-ja.wav",
        filename_prefix="aifilm/talking/infinite-stable",
    )
    assert graph["1"]["inputs"]["image"] == "approved/hero.png"
    assert graph["2"]["inputs"]["audio"] == "approved/hero-ja.wav"
    assert graph["4"]["inputs"]["audio_scale"] == 1.0
    assert graph["4"]["inputs"]["num_frames"] == 193
    assert weapon["defaults"]["num_frames"] == 193
    assert graph["9"]["inputs"]["positive_prompt"].startswith("The adult character")
    assert graph["11"]["inputs"]["seed"] == 20260729
    assert graph["13"]["inputs"]["filename_prefix"] == "aifilm/talking/infinite-stable"


def test_compile_fantasy_talking_accepts_only_registered_quality_steps() -> None:
    graph = compile_weapon_workflow(
        "fantasy-talking-6step-pilot",
        prompt="The adult character speaks with expressive but natural mouth motion.",
        seed=20260729,
        input_image_name="approved/hero.png",
        input_audio_name="approved/hero-ja.wav",
        steps=30,
    )
    assert graph["13"]["inputs"]["steps"] == 30
    with pytest.raises(ComfyArmoryError, match="registered step"):
        compile_weapon_workflow(
            "fantasy-talking-6step-pilot",
            prompt="The character speaks.",
            seed=7,
            input_image_name="approved/hero.png",
            input_audio_name="approved/hero.wav",
            steps=20,
        )


def test_compile_talking_avatar_requires_uploaded_audio_name() -> None:
    with pytest.raises(ComfyArmoryError, match="audio"):
        compile_weapon_workflow(
            "infinite-talk-stable-pilot",
            prompt="The character speaks.",
            seed=7,
            input_image_name="approved/hero.png",
        )


@patch("comfy_armory._json_request")
def test_registered_talking_workflow_accepts_only_exact_custom_node_modules(
    request: MagicMock,
) -> None:
    graph = compile_weapon_workflow(
        "infinite-talk-stable-pilot",
        prompt="The character speaks.",
        seed=7,
        input_image_name="approved/hero.png",
        input_audio_name="approved/hero.wav",
    )

    def node_info(_url: str, route: str) -> dict[str, object]:
        class_type = route.rsplit("/", 1)[-1]
        trusted = {
            "LoadImage": "nodes",
            "LoadAudio": "comfy_extras.nodes_audio",
            "DownloadAndLoadWav2VecModel": "custom_nodes.ComfyUI-WanVideoWrapper",
            "MultiTalkWav2VecEmbeds": "custom_nodes.ComfyUI-WanVideoWrapper",
            "MultiTalkModelLoader": "custom_nodes.ComfyUI-WanVideoWrapper",
            "WanVideoBlockSwap": "custom_nodes.ComfyUI-WanVideoWrapper",
            "WanVideoModelLoader": "custom_nodes.ComfyUI-WanVideoWrapper",
            "WanVideoVAELoader": "custom_nodes.ComfyUI-WanVideoWrapper",
            "WanVideoTextEncodeCached": "custom_nodes.ComfyUI-WanVideoWrapper",
            "WanVideoImageToVideoMultiTalk": "custom_nodes.ComfyUI-WanVideoWrapper",
            "WanVideoSampler": "custom_nodes.ComfyUI-WanVideoWrapper",
            "WanVideoPassImagesFromSamples": "custom_nodes.ComfyUI-WanVideoWrapper",
            "VHS_VideoCombine": "custom_nodes.comfyui-videohelpersuite",
        }
        return {
            class_type: {
                "python_module": trusted[class_type],
                "category": "local",
                "api_node": False,
            }
        }

    request.side_effect = node_info
    assert_registered_weapon_workflow(
        "https://192.168.88.52:8188",
        "infinite-talk-stable-pilot",
        graph,
    )

    request.side_effect = lambda _url, route: {
        route.rsplit("/", 1)[-1]: {
            "python_module": "custom_nodes.untrusted-fork",
            "category": "local",
            "api_node": False,
        }
    }
    with pytest.raises(ComfyArmoryError, match="untrusted node module"):
        assert_registered_weapon_workflow(
            "https://192.168.88.52:8188",
            "infinite-talk-stable-pilot",
            graph,
        )


def test_registered_talking_workflow_rejects_nonbinding_tampering() -> None:
    graph = compile_weapon_workflow(
        "infinite-talk-stable-pilot",
        prompt="The character speaks.",
        seed=7,
        input_image_name="approved/hero.png",
        input_audio_name="approved/hero.wav",
    )
    graph["4"]["inputs"]["audio_scale"] = 4.0
    with pytest.raises(ComfyArmoryError, match="unapproved workflow mutation"):
        assert_registered_weapon_workflow(
            "https://192.168.88.52:8188",
            "infinite-talk-stable-pilot",
            graph,
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
        "/models/checkpoints": [],
        "/models/diffusion_models": [
            "qwen_image_2512_fp8_e4m3fn.safetensors",
            "qwen_image_edit_2511_fp8mixed.safetensors",
        ],
        "/models/text_encoders": ["qwen_2.5_vl_7b_fp8_scaled.safetensors"],
        "/models/vae": ["qwen_image_vae.safetensors"],
        "/models/loras": ["Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"],
        "/models/clip_vision": [],
        "/models/latent_upscale_models": [],
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
        "wan22-i2v-portrait-pilot",
        "wan22-adult-intimacy-baseline",
        "wan22-adult-meat-pilot",
        "infinite-talk-stable-pilot",
        "fantasy-talking-6step-pilot",
        "hunyuan15-720p-i2v-sr-pilot",
        "ace-step15-xl-rnb-pilot",
        "ltx23-native-i2v-pilot",
        "ltx23-distilled-fp8-fast-broll-pilot",
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
        for group in (
            "checkpoints",
            "diffusion_models",
            "text_encoders",
            "vae",
            "loras",
            "clip_vision",
            "latent_upscale_models",
        )
    }
    request.side_effect = lambda _url, route: installed[route.removeprefix("/models/")]
    model_sha256.side_effect = ComfyArmoryError("metadata unavailable")

    report = probe_armory("https://192.168.88.52:8188")

    assert "wan22-i2v-quality" in report["ready_ids"]
    assert "qwen-image-2512-quality" in report["ready_ids"]
    blocked = {item["id"]: item for item in report["blocked"]}
    assert set(blocked) == {
        "wan22-adult-meat-pilot",
        "infinite-talk-stable-pilot",
        "fantasy-talking-6step-pilot",
        "hunyuan15-720p-i2v-sr-pilot",
        "ace-step15-xl-rnb-pilot",
        "ltx23-native-i2v-pilot",
    }
    assert blocked["wan22-adult-meat-pilot"]["sha256_errors"]["loras"]
    assert blocked["ace-step15-xl-rnb-pilot"]["sha256_errors"]["diffusion_models"]
    assert blocked["ltx23-native-i2v-pilot"]["sha256_errors"]["checkpoints"]


@patch("comfy_armory._model_sha256", return_value="0" * 64)
@patch("comfy_armory._json_request")
def test_live_probe_blocks_same_name_adult_lora_with_wrong_hash(
    request: MagicMock,
    _sha256: MagicMock,
) -> None:
    request.side_effect = lambda _url, route: {
        "/models/checkpoints": [],
        "/models/diffusion_models": [
            "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
            "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
        ],
        "/models/text_encoders": ["umt5_xxl_fp8_e4m3fn_scaled.safetensors"],
        "/models/vae": ["wan_2.1_vae.safetensors"],
        "/models/loras": ["NSFW-22-H-e8.safetensors", "NSFW-22-L-e8.safetensors"],
        "/models/clip_vision": [],
        "/models/latent_upscale_models": [],
    }[route]
    report = probe_armory("https://192.168.88.52:8188")
    blocked = {item["id"]: item for item in report["blocked"]}
    assert "wan22-adult-meat-pilot" in blocked
    assert blocked["wan22-adult-meat-pilot"]["sha256_mismatches"]


@patch("comfy_armory._json_request")
def test_live_probe_accepts_exact_adult_lora_hashes(request: MagicMock) -> None:
    request.side_effect = lambda _url, route: {
        "/models/checkpoints": [],
        "/models/diffusion_models": [
            "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
            "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
        ],
        "/models/text_encoders": ["umt5_xxl_fp8_e4m3fn_scaled.safetensors"],
        "/models/vae": ["wan_2.1_vae.safetensors"],
        "/models/loras": ["NSFW-22-H-e8.safetensors", "NSFW-22-L-e8.safetensors"],
        "/models/clip_vision": [],
        "/models/latent_upscale_models": [],
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
