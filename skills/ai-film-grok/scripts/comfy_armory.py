"""Verified demand router for the user's private RTX 5090 ComfyUI armory."""

from __future__ import annotations

import json
import os
import re
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
    data = armory or load_armory()
    node = data["nodes"].get(data["default_node"]) or {}
    configured = os.environ.get("AIFILM_COMFYUI_BASE_URL", "").strip()
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
    if normalized == "adult-meat-motion-i2v":
        normalized_stage = str(stage).strip().lower()
        if normalized_stage not in {"pilot", "production"}:
            raise ComfyArmoryError(f"unsupported production stage: {stage}")
        if normalized_stage == "production":
            raise ComfyArmoryError(
                "no promoted Wan 2.2 weapon meets the adult meat-motion production gate"
            )
        if not allow_experimental:
            raise ComfyArmoryError(
                "adult meat-motion pilot requires explicit experimental authorization"
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


def compile_weapon_workflow(
    weapon_id: str,
    *,
    prompt: str,
    seed: int,
    input_image_name: str | None = None,
    filename_prefix: str = "aifilm/armory",
) -> dict[str, dict[str, Any]]:
    """Bind a verified image workflow template without submitting it."""
    if not str(prompt).strip():
        raise ComfyArmoryError("prompt must not be empty")
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2**64:
        raise ComfyArmoryError("seed must be an integer from 0 through 2^64-1")
    weapon = next(
        (item for item in load_armory()["weapons"] if item["id"] == weapon_id),
        None,
    )
    if weapon is None:
        raise ComfyArmoryError(f"unknown verified weapon: {weapon_id}")
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
