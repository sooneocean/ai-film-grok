"""Verified demand router for the user's private RTX 5090 ComfyUI armory."""

from __future__ import annotations

import json
import os
import re
import urllib.parse
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from comfy_video import _json_request, _model_sha256, normalize_base_url


class ComfyArmoryError(RuntimeError):
    pass


_SKILL_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY = _SKILL_ROOT / "registry" / "comfy-weapons.json"
_MODEL_ROUTES = {
    "checkpoints": "/models/checkpoints",
    "diffusion_models": "/models/diffusion_models",
    "text_encoders": "/models/text_encoders",
    "vae": "/models/vae",
    "loras": "/models/loras",
    "clip_vision": "/models/clip_vision",
    "latent_upscale_models": "/models/latent_upscale_models",
}
_SAFE_PREFIX = re.compile(r"[A-Za-z0-9_./-]+")
_VERIFIED_STATUSES = frozenset({"verified", "verified-baseline"})


def load_armory() -> dict[str, Any]:
    try:
        data = json.loads(_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ComfyArmoryError(f"cannot read Comfy armory registry: {exc}") from exc
    if not isinstance(data.get("weapons"), list) or not data.get("default_node"):
        raise ComfyArmoryError("invalid Comfy armory registry")
    serialized = json.dumps(data, ensure_ascii=False).lower()
    if any(secret in serialized for secret in ('"password"', '"token"', '"private_key"')):
        raise ComfyArmoryError("Comfy armory registry must not contain credentials")
    data["ok"] = True
    return data


def default_base_url(armory: dict[str, Any] | None = None) -> str:
    data = armory if armory is not None else load_armory()
    node = data["nodes"].get(data["default_node"]) or {}
    configured = os.environ.get("AIFILM_COMFYUI_BASE_URL", "").strip() if armory is None else ""
    value = configured or str(node.get("base_url") or "")
    if not value:
        raise ComfyArmoryError("verified armory node has no base URL")
    return normalize_base_url(value)


def _select_candidates(
    operation: str,
    *,
    quality: str,
    identity_lock: bool,
    ready_ids: set[str] | None,
    stage: str,
    allow_experimental: bool,
) -> list[dict[str, Any]]:
    candidates = []
    for weapon in load_armory()["weapons"]:
        status = str(weapon.get("status") or "")
        is_experimental = status == "experimental"
        if status not in _VERIFIED_STATUSES and not (is_experimental and allow_experimental):
            continue
        if is_experimental and stage != "pilot":
            continue
        is_authorized_first_pilot = is_experimental and stage == "pilot" and allow_experimental
        if (weapon.get("verified") or {}).get(
            "real_pilot"
        ) is not True and not is_authorized_first_pilot:
            continue
        if operation not in weapon.get("intents", []):
            continue
        if quality not in weapon.get("quality_tiers", []):
            continue
        if identity_lock and not weapon.get("capabilities", {}).get(
            "identity_preserving_local_edit"
        ):
            continue
        if ready_ids is not None and weapon["id"] not in ready_ids:
            continue
        candidates.append(weapon)
    return sorted(candidates, key=lambda item: int(item.get("priority", 0)), reverse=True)


def select_weapon(
    operation: str,
    *,
    quality: str = "max_practical",
    identity_lock: bool = False,
    ready_ids: set[str] | None = None,
    stage: str = "production",
    allow_experimental: bool = False,
) -> dict[str, Any]:
    """Select from structured intent; free-form prompt guessing is forbidden."""
    normalized = str(operation).strip().lower()
    normalized_stage = str(stage).strip().lower()
    if normalized_stage not in {"pilot", "production"}:
        raise ComfyArmoryError(f"unsupported production stage: {stage}")
    # Local Wan 2.2 I2V remains retired. MiniMax H3 owns local motion intents
    # when production-promoted (hybrid restricted/meat + explicit aifilm h3).
    # Unpromoted experimental H3 still requires --allow-experimental at pilot.
    if normalized in {
        "image-to-video",
        "i2v",
        "general-i2v",
        "adult-intimacy-i2v",
        "adult-meat-motion-i2v",
        "text-to-video",
        "t2v",
        "reference-to-video",
        "r2v",
        "minimax-h3-t2v",
        "minimax-h3-i2v",
        "minimax-h3-r2v",
    }:
        promoted = any(
            str(item.get("id") or "").startswith("minimax-h3-")
            and (item.get("verified") or {}).get("production_promoted") is True
            and str(item.get("status") or "") in _VERIFIED_STATUSES
            for item in load_armory()["weapons"]
        )
        if not promoted and normalized_stage == "pilot" and not allow_experimental:
            raise ComfyArmoryError(
                "local MiniMax H3 motion pilot requires explicit experimental authorization "
                "(--allow-experimental) until a weapon is production-promoted"
            )
        if (
            not promoted
            and normalized == "adult-meat-motion-i2v"
            and normalized_stage == "production"
        ):
            raise ComfyArmoryError(
                "no promoted local weapon meets the adult meat-motion production gate"
            )
    if normalized in {
        "talking-avatar-stable-pilot",
        "talking-avatar-expressive-pilot",
    }:
        if normalized_stage != "pilot":
            raise ComfyArmoryError("talking-avatar armory routes are pilot-only")
        if not allow_experimental:
            raise ComfyArmoryError(
                "talking-avatar pilot requires explicit experimental authorization"
            )
    candidates = _select_candidates(
        normalized,
        quality=quality,
        identity_lock=identity_lock,
        ready_ids=ready_ids,
        stage=normalized_stage,
        allow_experimental=allow_experimental,
    )
    if not candidates:
        raise ComfyArmoryError(f"no verified weapon for operation: {operation}")
    return {
        "schema_version": 1,
        "kind": "comfy-armory-selection",
        "ok": True,
        "operation": str(operation).strip().lower(),
        "intent": str(operation).strip().lower(),
        "quality": quality,
        "weapon": deepcopy(candidates[0]),
    }


def _template_path(weapon: dict[str, Any]) -> Path:
    raw = str(weapon.get("workflow_template") or "")
    path = (_SKILL_ROOT / raw).resolve()
    if not raw or not path.is_relative_to(_SKILL_ROOT) or not path.is_file():
        raise ComfyArmoryError(f"workflow template unavailable for weapon: {weapon['id']}")
    return path


def _weapon(weapon_id: str) -> dict[str, Any]:
    weapon = next(
        (item for item in load_armory()["weapons"] if item["id"] == weapon_id),
        None,
    )
    if weapon is None:
        raise ComfyArmoryError(f"unknown verified weapon: {weapon_id}")
    return weapon


def _enforce_prompt_contract(weapon: Mapping[str, Any], prompt: str) -> None:
    """Reject declared pilot exclusions before a workflow can reach the node."""
    forbidden = weapon.get("prompt_forbidden_patterns") or []
    if not isinstance(forbidden, list):
        raise ComfyArmoryError("weapon prompt contract must be a list")
    for pattern in forbidden:
        if not isinstance(pattern, str) or not pattern:
            raise ComfyArmoryError("weapon prompt contract contains an invalid pattern")
        if re.search(pattern, prompt, flags=re.IGNORECASE):
            raise ComfyArmoryError(
                f"prompt violates the declared pilot contract for weapon: {weapon['id']}"
            )


def authorize_weapon_execution(
    weapon_id: str,
    *,
    stage: str,
    allow_experimental: bool,
) -> dict[str, Any]:
    weapon = _weapon(weapon_id)
    normalized_stage = str(stage).strip().lower()
    if normalized_stage not in {"pilot", "production"}:
        raise ComfyArmoryError(f"unsupported production stage: {stage}")
    if weapon.get("status") == "experimental":
        if normalized_stage != "pilot":
            raise ComfyArmoryError(f"experimental weapon {weapon_id} is pilot-only")
        if not allow_experimental:
            raise ComfyArmoryError(
                f"experimental weapon {weapon_id} requires explicit authorization"
            )
    elif weapon.get("status") not in _VERIFIED_STATUSES:
        raise ComfyArmoryError(f"weapon {weapon_id} is not eligible for execution")
    return weapon


def _validate_relative_media_name(value: str, *, label: str) -> str:
    candidate = str(value).strip().replace("\\", "/")
    if (
        not candidate
        or not _SAFE_PREFIX.fullmatch(candidate)
        or candidate.startswith("/")
        or any(part in {"", ".", ".."} for part in candidate.split("/"))
    ):
        raise ComfyArmoryError(f"{label} must be a safe relative ComfyUI media path")
    return candidate


def _allowed_binding_slots(bindings: Mapping[str, Any]) -> set[tuple[str, str]]:
    pairs = (
        ("prompt_node", "prompt_input"),
        ("sampler_node", "seed_input"),
        ("steps_node", "steps_input"),
        ("save_node", "filename_prefix_input"),
        ("input_node", "input_image_input"),
        ("audio_node", "audio_input"),
        ("last_input_node", "last_image_input"),
    )
    slots = {
        (str(bindings[node_key]), str(bindings[input_key]))
        for node_key, input_key in pairs
        if node_key in bindings and input_key in bindings
    }
    for key, input_key in (
        ("additional_seed_nodes", "seed_input"),
        ("additional_steps_nodes", "steps_input"),
    ):
        if key in bindings and input_key in bindings:
            slots.update((str(node), str(bindings[input_key])) for node in bindings[key])
    if "last_frame_node" in bindings and "last_frame_input" in bindings:
        slots.add((str(bindings["last_frame_node"]), str(bindings["last_frame_input"])))
    for node_id in bindings.get("ref_input_nodes") or []:
        slots.add((str(node_id), str(bindings.get("ref_image_input") or "image")))
    # Multi-ref links on MiniMaxH3ReferenceToVideo (ref_images.ref_image_N)
    frame_node = str(bindings.get("ref_frame_node") or bindings.get("prompt_node") or "")
    for key in bindings.get("ref_frame_inputs") or []:
        if frame_node:
            slots.add((frame_node, str(key)))
    return slots


def _optional_last_frame_nodes(bindings: Mapping[str, Any]) -> set[str]:
    """Nodes that may be injected for last_frame / multi-ref (not in base template)."""
    out: set[str] = set()
    if bindings.get("last_input_node"):
        out.add(str(bindings["last_input_node"]))
    for node_id in bindings.get("ref_input_nodes") or []:
        # Primary input_node is already in the template; only extras are optional.
        if str(node_id) != str(bindings.get("input_node") or ""):
            out.add(str(node_id))
    return out


def _matches_registered_template(
    graph: Mapping[str, Any],
    weapon: Mapping[str, Any],
) -> bool:
    try:
        template = json.loads(_template_path(dict(weapon)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    bindings = weapon.get("bindings") or {}
    optional_nodes = _optional_last_frame_nodes(bindings)
    if set(graph) - optional_nodes != set(template):
        return False
    if not set(template).issubset(set(graph)):
        return False
    allowed_slots = _allowed_binding_slots(bindings)
    for node_id, expected_node in template.items():
        actual_node = graph.get(node_id)
        if not isinstance(actual_node, Mapping) or actual_node.get(
            "class_type"
        ) != expected_node.get("class_type"):
            return False
        if set(actual_node) != set(expected_node):
            return False
        actual_inputs = actual_node.get("inputs")
        expected_inputs = expected_node.get("inputs")
        if not isinstance(actual_inputs, Mapping) or not isinstance(expected_inputs, Mapping):
            return False
        extra = set(actual_inputs) - set(expected_inputs)
        missing = set(expected_inputs) - set(actual_inputs)
        if missing:
            return False
        if extra and any((str(node_id), str(name)) not in allowed_slots for name in extra):
            return False
        if any(
            actual_inputs[input_name] != expected_value
            and (str(node_id), str(input_name)) not in allowed_slots
            for input_name, expected_value in expected_inputs.items()
        ):
            return False
    for node_id in set(graph) - set(template):
        if node_id not in optional_nodes:
            return False
        node = graph.get(node_id)
        if not isinstance(node, Mapping) or node.get("class_type") != "LoadImage":
            return False
    return True


def identify_registered_weapon_workflow(
    graph: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Recognize registered templates even when the caller omits --weapon-id."""
    weapons = [weapon for weapon in load_armory()["weapons"] if weapon.get("workflow_template")]
    matches = [weapon for weapon in weapons if _matches_registered_template(graph, weapon)]
    if len(matches) > 1:
        raise ComfyArmoryError("workflow matches multiple registered weapons; --weapon-id required")
    if matches:
        return deepcopy(matches[0])

    class_types = {
        str(node.get("class_type"))
        for node in graph.values()
        if isinstance(node, Mapping) and node.get("class_type")
    }
    armory = load_armory()
    protected: list[str] = []
    for weapon in list(armory["weapons"]) + list(armory.get("research_weapons") or []):
        if weapon.get("status") != "experimental":
            continue
        protected_classes = {
            str(value)
            for value in (
                *(weapon.get("protected_class_types") or []),
                *(weapon.get("trusted_custom_nodes") or {}).keys(),
            )
        }
        protected_prefixes = tuple(
            str(value) for value in (weapon.get("protected_class_type_prefixes") or [])
        )
        if class_types.intersection(protected_classes) or any(
            class_type.startswith(protected_prefixes)
            for class_type in class_types
            if protected_prefixes
        ):
            protected.append(str(weapon["id"]))
    protected.sort()
    if protected:
        raise ComfyArmoryError(
            "workflow uses nodes reserved for registered experimental weapons; "
            f"--weapon-id required ({', '.join(protected)})"
        )
    return None


def assert_registered_weapon_workflow(
    base_url: str,
    weapon_id: str,
    graph: Mapping[str, Any],
) -> dict[str, Any]:
    """Allow exact registered templates with changes only at typed compiler bindings."""
    weapon = _weapon(weapon_id)
    try:
        template = json.loads(_template_path(weapon).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ComfyArmoryError(f"cannot read workflow template: {exc}") from exc
    audio_extension = weapon.get("audio_conditioning_extension") or {}
    extension_nodes = {
        str(audio_extension.get("source_node") or ""),
        str(audio_extension.get("encode_node") or ""),
    } - {""}
    bindings = weapon.get("bindings") or {}
    optional_last_nodes = _optional_last_frame_nodes(bindings)
    allowed_extra_nodes = extension_nodes | optional_last_nodes
    if not set(template).issubset(set(graph)):
        raise ComfyArmoryError("unapproved workflow mutation: node set changed")
    if not set(graph).issubset(set(template) | allowed_extra_nodes):
        raise ComfyArmoryError("unapproved workflow mutation: node set changed")
    allowed_slots = _allowed_binding_slots(bindings)
    if extension_nodes:
        latent_node = str(audio_extension.get("latent_node") or "")
        latent_input = str(audio_extension.get("latent_input") or "")
        allowed_slots.add((latent_node, latent_input))
        for frame_node, frame_input in audio_extension.get("frame_slots") or []:
            allowed_slots.add((str(frame_node), str(frame_input)))
    for node_id, expected_node in template.items():
        actual_node = graph.get(node_id)
        if not isinstance(actual_node, Mapping):
            raise ComfyArmoryError(f"unapproved workflow mutation at node {node_id}")
        if set(actual_node) != set(expected_node):
            raise ComfyArmoryError(f"unapproved workflow mutation at node {node_id}")
        if actual_node.get("class_type") != expected_node.get("class_type"):
            raise ComfyArmoryError(f"unapproved workflow mutation at node {node_id}")
        actual_inputs = actual_node.get("inputs")
        expected_inputs = expected_node.get("inputs")
        if not isinstance(actual_inputs, Mapping) or not isinstance(expected_inputs, Mapping):
            raise ComfyArmoryError(f"unapproved workflow mutation at node {node_id}")
        if set(expected_inputs) - set(actual_inputs):
            raise ComfyArmoryError(f"unapproved workflow mutation at node {node_id}")
        extra_inputs = set(actual_inputs) - set(expected_inputs)
        if extra_inputs and any(
            (str(node_id), str(name)) not in allowed_slots for name in extra_inputs
        ):
            raise ComfyArmoryError(f"unapproved workflow mutation at node {node_id}")
        for input_name, expected_value in expected_inputs.items():
            if (
                actual_inputs[input_name] != expected_value
                and (str(node_id), str(input_name)) not in allowed_slots
            ):
                raise ComfyArmoryError(f"unapproved workflow mutation at {node_id}.{input_name}")
    for node_id in set(graph) & optional_last_nodes:
        node = graph.get(node_id)
        if not isinstance(node, Mapping) or node.get("class_type") != "LoadImage":
            raise ComfyArmoryError(f"unapproved last-frame LoadImage at node {node_id}")
        img = (node.get("inputs") or {}).get("image")
        _validate_relative_media_name(str(img), label="last frame image name")
        frame_node = str(bindings.get("last_frame_node") or "")
        frame_input = str(bindings.get("last_frame_input") or "last_frame")
        if frame_node:
            link = (graph.get(frame_node) or {}).get("inputs", {}).get(frame_input)
            if link != [node_id, 0]:
                raise ComfyArmoryError("last_frame link must point at last LoadImage node")

    if extension_nodes:
        source_node = str(audio_extension["source_node"])
        encode_node = str(audio_extension["encode_node"])
        latent_node = str(audio_extension["latent_node"])
        latent_input = str(audio_extension["latent_input"])
        audio_vae_node = str(audio_extension["audio_vae_node"])
        audio_name = graph.get(source_node, {}).get("inputs", {}).get("audio")
        expected_source = {"class_type": "LoadAudio", "inputs": {"audio": audio_name}}
        expected_encode = {
            "class_type": "LTXVAudioVAEEncode",
            "inputs": {"audio": [source_node, 0], "audio_vae": [audio_vae_node, 0]},
        }
        if graph.get(source_node) != expected_source or graph.get(encode_node) != expected_encode:
            raise ComfyArmoryError("unapproved LTX audio-conditioning extension")
        if graph[latent_node]["inputs"][latent_input] != [encode_node, 0]:
            raise ComfyArmoryError("LTX audio-conditioning latent link is invalid")
        frame_values = [
            graph[str(node)]["inputs"][str(input_name)]
            for node, input_name in audio_extension.get("frame_slots") or []
        ]
        if (
            not frame_values
            or len(set(frame_values)) != 1
            or not isinstance(frame_values[0], int)
            or not 9 <= frame_values[0] <= 241
            or (frame_values[0] != 126 and (frame_values[0] - 1) % 8)
        ):
            raise ComfyArmoryError("LTX audio-conditioning frame length is invalid")
        _validate_relative_media_name(str(audio_name), label="input audio name")

    prompt = graph[str(bindings["prompt_node"])]["inputs"][str(bindings["prompt_input"])]
    seed = graph[str(bindings["sampler_node"])]["inputs"][str(bindings["seed_input"])]
    filename_prefix = graph[str(bindings["save_node"])]["inputs"][
        str(bindings["filename_prefix_input"])
    ]
    if not isinstance(prompt, str) or not prompt.strip():
        raise ComfyArmoryError("compiled workflow prompt must not be empty")
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**64:
        raise ComfyArmoryError("compiled workflow seed is invalid")
    if "steps_node" in bindings:
        steps = graph[str(bindings["steps_node"])]["inputs"][str(bindings["steps_input"])]
        allowed_steps = (weapon.get("tuning") or {}).get("steps", {}).get("allowed") or []
        if not isinstance(steps, int) or isinstance(steps, bool) or steps not in allowed_steps:
            raise ComfyArmoryError("compiled workflow steps are not a registered step value")
    _validate_relative_media_name(str(filename_prefix), label="filename prefix")
    if "input_node" in bindings:
        _validate_relative_media_name(
            str(graph[str(bindings["input_node"])]["inputs"][str(bindings["input_image_input"])]),
            label="input image name",
        )
    if "audio_node" in bindings:
        _validate_relative_media_name(
            str(graph[str(bindings["audio_node"])]["inputs"][str(bindings["audio_input"])]),
            label="input audio name",
        )

    trusted_custom_nodes = weapon.get("trusted_custom_nodes") or {}
    trusted_custom_node_prefixes = weapon.get("trusted_custom_node_prefixes") or {}
    for class_type in sorted(
        {
            str(node["class_type"])
            for node in graph.values()
            if isinstance(node, Mapping) and node.get("class_type")
        }
    ):
        data = _json_request(
            base_url,
            f"/object_info/{urllib.parse.quote(class_type, safe='')}",
        )
        info = data.get(class_type, data) if isinstance(data, dict) else {}
        if not isinstance(info, Mapping) or not info:
            raise ComfyArmoryError(f"workflow node metadata unavailable: {class_type}")
        if info.get("api_node") or str(info.get("category") or "").lower().startswith("api node"):
            raise ComfyArmoryError(f"registered workflow contains external API node: {class_type}")
        python_module = str(info.get("python_module") or "")
        if python_module == "nodes" or python_module.startswith("comfy_extras."):
            continue
        expected_module = trusted_custom_nodes.get(class_type)
        if expected_module is None:
            expected_module = next(
                (
                    module
                    for prefix, module in trusted_custom_node_prefixes.items()
                    if class_type.startswith(str(prefix))
                ),
                None,
            )
        if expected_module != python_module:
            raise ComfyArmoryError(
                f"untrusted node module for {class_type}: {python_module or 'unknown'}"
            )
    return weapon


def compile_weapon_workflow(
    weapon_id: str,
    *,
    prompt: str,
    seed: int,
    input_image_name: str | None = None,
    last_image_name: str | None = None,
    ref_image_names: list[str] | None = None,
    input_audio_name: str | None = None,
    filename_prefix: str = "aifilm/armory",
    steps: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Bind a verified image workflow template without submitting it.

    Optional ``last_image_name`` injects MiniMax H3 first/last-frame (FLF) wiring
    when the weapon declares ``last_input_node`` / ``last_frame_node`` bindings.
    """
    if not str(prompt).strip():
        raise ComfyArmoryError("prompt must not be empty")
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**64:
        raise ComfyArmoryError("seed must be an integer from 0 through 2^64-1")
    weapon = _weapon(weapon_id)
    _enforce_prompt_contract(weapon, str(prompt))
    filename_prefix = _validate_relative_media_name(filename_prefix, label="filename prefix")
    if not weapon.get("workflow_template"):
        raise ComfyArmoryError(
            f"workflow compiler is unavailable for weapon: {weapon_id}; use its provider"
        )
    try:
        graph = json.loads(_template_path(weapon).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ComfyArmoryError(f"cannot read workflow template: {exc}") from exc
    bindings = weapon["bindings"]
    graph[bindings["prompt_node"]]["inputs"][bindings["prompt_input"]] = prompt
    graph[bindings["sampler_node"]]["inputs"][bindings["seed_input"]] = seed
    for node_id in bindings.get("additional_seed_nodes", []):
        graph[node_id]["inputs"][bindings["seed_input"]] = seed
    graph[bindings["save_node"]]["inputs"][bindings["filename_prefix_input"]] = filename_prefix
    if "steps_node" in bindings:
        selected_steps = weapon.get("defaults", {}).get("steps") if steps is None else steps
        allowed_steps = (weapon.get("tuning") or {}).get("steps", {}).get("allowed") or []
        if (
            not isinstance(selected_steps, int)
            or isinstance(selected_steps, bool)
            or selected_steps not in allowed_steps
        ):
            raise ComfyArmoryError("steps must be a registered step value for this weapon")
        graph[bindings["steps_node"]]["inputs"][bindings["steps_input"]] = selected_steps
        for node_id in bindings.get("additional_steps_nodes", []):
            graph[node_id]["inputs"][bindings["steps_input"]] = selected_steps
    if "input_node" in bindings:
        if not input_image_name:
            raise ComfyArmoryError(f"weapon {weapon_id} requires an uploaded input image name")
        input_image_name = _validate_relative_media_name(input_image_name, label="input image name")
        graph[bindings["input_node"]]["inputs"][bindings["input_image_input"]] = input_image_name
    for node in graph.values():
        if not isinstance(node, dict):
            continue
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for key, value in list(inputs.items()):
            if value == "__AIFILM_PROMPT__":
                inputs[key] = prompt
            if value == "__AIFILM_INPUT_IMAGE__" and input_image_name:
                inputs[key] = input_image_name
            if value == "__AIFILM_LAST_IMAGE__" and last_image_name:
                inputs[key] = last_image_name
    # Optional last-frame (FLF): inject LoadImage + last_frame link when requested.
    if last_image_name:
        last_node = str(bindings.get("last_input_node") or "").strip()
        frame_node = str(bindings.get("last_frame_node") or "").strip()
        frame_input = str(bindings.get("last_frame_input") or "last_frame")
        last_img_key = str(bindings.get("last_image_input") or "image")
        if not last_node or not frame_node:
            raise ComfyArmoryError(
                f"weapon {weapon_id} does not declare last_frame bindings; cannot bind last image"
            )
        last_image_name = _validate_relative_media_name(
            last_image_name, label="last frame image name"
        )
        if last_node in graph and graph[last_node].get("class_type") == "LoadImage":
            graph[last_node]["inputs"][last_img_key] = last_image_name
        else:
            graph[last_node] = {
                "class_type": "LoadImage",
                "inputs": {last_img_key: last_image_name},
            }
        if frame_node not in graph:
            raise ComfyArmoryError(f"weapon {weapon_id} missing last_frame node {frame_node}")
        graph[frame_node]["inputs"][frame_input] = [last_node, 0]
    if ref_image_names:
        ref_nodes = [str(n) for n in (bindings.get("ref_input_nodes") or [])]
        ref_key = str(bindings.get("ref_image_input") or "image")
        frame_node = str(bindings.get("ref_frame_node") or bindings.get("prompt_node") or "")
        frame_inputs = [str(x) for x in (bindings.get("ref_frame_inputs") or [])]
        if not ref_nodes and "input_node" not in bindings:
            raise ComfyArmoryError(
                f"weapon {weapon_id} has no ref_input_nodes for multi-reference binding"
            )
        for idx, ref_name in enumerate(ref_image_names):
            if idx >= len(ref_nodes):
                break
            node_id = ref_nodes[idx]
            safe = _validate_relative_media_name(str(ref_name), label=f"ref image {idx}")
            if node_id in graph and graph[node_id].get("class_type") == "LoadImage":
                graph[node_id]["inputs"][ref_key] = safe
            else:
                graph[node_id] = {"class_type": "LoadImage", "inputs": {ref_key: safe}}
            # Wire MiniMaxH3ReferenceToVideo.ref_images.ref_image_N when declared
            if frame_node and idx < len(frame_inputs) and frame_node in graph:
                graph[frame_node]["inputs"][frame_inputs[idx]] = [node_id, 0]
    if "audio_node" in bindings:
        if not input_audio_name:
            raise ComfyArmoryError("talking-avatar workflow requires an uploaded audio name")
        input_audio_name = _validate_relative_media_name(
            input_audio_name,
            label="input audio name",
        )
        graph[bindings["audio_node"]]["inputs"][bindings["audio_input"]] = input_audio_name
    return graph


def probe_armory(base_url: str | None = None) -> dict[str, Any]:
    armory = load_armory()
    url = normalize_base_url(base_url or default_base_url(armory))
    installed = {group: set(_json_request(url, route)) for group, route in _MODEL_ROUTES.items()}
    ready: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for weapon in armory["weapons"]:
        missing = {
            group: sorted(set(names) - installed[group])
            for group, names in weapon.get("requirements", {}).items()
            if set(names) - installed[group]
        }
        hash_mismatches: dict[str, dict[str, str]] = {}
        hash_errors: dict[str, dict[str, str]] = {}
        if not missing:
            for group, expected in weapon.get("requirement_sha256", {}).items():
                for filename, expected_hash in expected.items():
                    try:
                        actual_hash = _model_sha256(url, group, filename)
                    except Exception as exc:
                        hash_errors.setdefault(group, {})[filename] = str(exc)[:200]
                        continue
                    if actual_hash != expected_hash:
                        hash_mismatches.setdefault(group, {})[filename] = actual_hash
        entry = {"id": weapon["id"], "status": weapon["status"]}
        if missing or hash_mismatches or hash_errors:
            blocked.append(
                {
                    **entry,
                    "missing": missing,
                    "sha256_mismatches": hash_mismatches,
                    "sha256_errors": hash_errors,
                }
            )
        else:
            ready.append(entry)
    return {
        "schema_version": 1,
        "kind": "comfy-armory-probe",
        "ok": True,
        "base_url": url,
        "ready": ready,
        "ready_ids": [item["id"] for item in ready],
        "blocked": blocked,
    }
