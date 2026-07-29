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


_SKILL_ROOT = Path(__file__).resolve().parents[1]
_REGISTRY = _SKILL_ROOT / "registry" / "comfy-weapons.json"
_MODEL_ROUTES = {
    "diffusion_models": "/models/diffusion_models",
    "text_encoders": "/models/text_encoders",
    "vae": "/models/vae",
    "loras": "/models/loras",
    "clip_vision": "/models/clip_vision",
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
    allow_experimental: bool,
) -> list[dict[str, Any]]:
    candidates = []
    for weapon in load_armory()["weapons"]:
        status = str(weapon.get("status") or "")
        is_experimental = status == "experimental"
        if status not in _VERIFIED_STATUSES and not (is_experimental and allow_experimental):
            continue
        if (weapon.get("verified") or {}).get("real_pilot") is not True:
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
    if normalized == "adult-meat-motion-i2v":
        if normalized_stage == "production":
            raise ComfyArmoryError(
                "no promoted Wan 2.2 weapon meets the adult meat-motion production gate"
            )
        if not allow_experimental:
            raise ComfyArmoryError(
                "adult meat-motion pilot requires explicit experimental authorization"
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
        ("save_node", "filename_prefix_input"),
        ("input_node", "input_image_input"),
        ("audio_node", "audio_input"),
    )
    return {
        (str(bindings[node_key]), str(bindings[input_key]))
        for node_key, input_key in pairs
        if node_key in bindings and input_key in bindings
    }


def _matches_registered_template(
    graph: Mapping[str, Any],
    weapon: Mapping[str, Any],
) -> bool:
    try:
        template = json.loads(_template_path(dict(weapon)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if set(graph) != set(template):
        return False
    allowed_slots = _allowed_binding_slots(weapon.get("bindings") or {})
    for node_id, expected_node in template.items():
        actual_node = graph.get(node_id)
        if (
            not isinstance(actual_node, Mapping)
            or set(actual_node) != set(expected_node)
            or actual_node.get("class_type") != expected_node.get("class_type")
        ):
            return False
        actual_inputs = actual_node.get("inputs")
        expected_inputs = expected_node.get("inputs")
        if (
            not isinstance(actual_inputs, Mapping)
            or not isinstance(expected_inputs, Mapping)
            or set(actual_inputs) != set(expected_inputs)
        ):
            return False
        if any(
            actual_inputs[input_name] != expected_value
            and (str(node_id), str(input_name)) not in allowed_slots
            for input_name, expected_value in expected_inputs.items()
        ):
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
    protected = sorted(
        weapon["id"]
        for weapon in weapons
        if weapon.get("status") == "experimental"
        and class_types.intersection((weapon.get("trusted_custom_nodes") or {}).keys())
    )
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
    if set(graph) != set(template):
        raise ComfyArmoryError("unapproved workflow mutation: node set changed")
    bindings = weapon.get("bindings") or {}
    allowed_slots = _allowed_binding_slots(bindings)
    for node_id, expected_node in template.items():
        actual_node = graph.get(node_id)
        if not isinstance(actual_node, Mapping) or set(actual_node) != set(expected_node):
            raise ComfyArmoryError(f"unapproved workflow mutation at node {node_id}")
        if actual_node.get("class_type") != expected_node.get("class_type"):
            raise ComfyArmoryError(f"unapproved workflow mutation at node {node_id}")
        actual_inputs = actual_node.get("inputs")
        expected_inputs = expected_node.get("inputs")
        if (
            not isinstance(actual_inputs, Mapping)
            or not isinstance(expected_inputs, Mapping)
            or set(actual_inputs) != set(expected_inputs)
        ):
            raise ComfyArmoryError(f"unapproved workflow mutation at node {node_id}")
        for input_name, expected_value in expected_inputs.items():
            if (
                actual_inputs[input_name] != expected_value
                and (str(node_id), str(input_name)) not in allowed_slots
            ):
                raise ComfyArmoryError(f"unapproved workflow mutation at {node_id}.{input_name}")

    prompt = graph[str(bindings["prompt_node"])]["inputs"][str(bindings["prompt_input"])]
    seed = graph[str(bindings["sampler_node"])]["inputs"][str(bindings["seed_input"])]
    filename_prefix = graph[str(bindings["save_node"])]["inputs"][
        str(bindings["filename_prefix_input"])
    ]
    if not isinstance(prompt, str) or not prompt.strip():
        raise ComfyArmoryError("compiled workflow prompt must not be empty")
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**64:
        raise ComfyArmoryError("compiled workflow seed is invalid")
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
        if trusted_custom_nodes.get(class_type) != python_module:
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
    input_audio_name: str | None = None,
    filename_prefix: str = "aifilm/armory",
) -> dict[str, dict[str, Any]]:
    """Bind a verified image workflow template without submitting it."""
    if not str(prompt).strip():
        raise ComfyArmoryError("prompt must not be empty")
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**64:
        raise ComfyArmoryError("seed must be an integer from 0 through 2^64-1")
    weapon = _weapon(weapon_id)
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
    graph[bindings["save_node"]]["inputs"][bindings["filename_prefix_input"]] = filename_prefix
    if "input_node" in bindings:
        if not input_image_name:
            raise ComfyArmoryError("Qwen local edit requires an input image name")
        input_image_name = _validate_relative_media_name(input_image_name, label="input image name")
        graph[bindings["input_node"]]["inputs"][bindings["input_image_input"]] = input_image_name
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
