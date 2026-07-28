#!/usr/bin/env python3
"""Private ComfyUI video client for the user's RTX 5090 node.

The production default remains Grok.  This module exposes an explicit local
Wan 2.2 lane with model/read-back evidence and no cloud upload.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import ipaddress
import json
import mimetypes
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from util import write_json


class ComfyVideoError(RuntimeError):
    pass


class _WebSocketUnavailable(RuntimeError):
    pass


WAN22_OFFICIAL_PROFILE: dict[str, str] = {
    "name": "official",
    "high": "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
    "low": "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
    "high_lora": "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors",
    "low_lora": "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors",
}

WAN22_ADULT_PROFILE: dict[str, str] = {
    "name": "adult-motion",
    "high": WAN22_OFFICIAL_PROFILE["high"],
    "low": WAN22_OFFICIAL_PROFILE["low"],
    # Provenance-poor merged weights and act-specific LoRAs stay out until A/B review.
    "high_lora": "",
    "low_lora": "",
}

WAN22_VAE = "wan_2.1_vae.safetensors"
WAN22_TEXT_ENCODER = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
DEFAULT_NEGATIVE = (
    "overexposed, static frame, blurry details, subtitles, watermark, low quality, "
    "jpeg artifacts, malformed anatomy, extra limbs, fused fingers, duplicate people, "
    "busy background, reverse motion"
)

_DISALLOWED_MINOR_SIGNALS = (
    re.compile(r"\bunderage\b", re.I),
    re.compile(r"\bminor\b", re.I),
    re.compile(r"\bschool[\s-]?girl\b", re.I),
    re.compile(r"\bschool[\s-]?boy\b", re.I),
    re.compile(r"\bteen(?:age|ager|aged|[\s-]?looking)?\b", re.I),
    re.compile(r"\bloli(?:con)?\b", re.I),
    re.compile(r"\bshota(?:con)?\b", re.I),
    re.compile(r"\bchild(?:ren)?\b", re.I),
)
_ALLOWED_SUBJECT_BASES = frozenset({"fictional_adults", "licensed_adults"})
_INVENTORY_MODEL_FOLDERS = frozenset(
    {
        "checkpoints",
        "diffusion_models",
        "unet_gguf",
        "text_encoders",
        "vae",
        "clip_vision",
        "loras",
        "controlnet",
        "upscale_models",
        "latent_upscale_models",
        "animatediff_models",
        "audio_encoders",
    }
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Mapping[str, str],
        newurl: str,
    ) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def normalize_base_url(raw: str) -> str:
    value = str(raw or "").strip().rstrip("/")
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError as exc:
        raise ComfyVideoError(f"invalid ComfyUI URL: {exc}") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ComfyVideoError("ComfyUI URL must be absolute http(s)")
    if (
        parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ComfyVideoError(
            "ComfyUI base URL cannot contain credentials, a path, query or fragment"
        )
    host = parsed.hostname
    if host == "localhost":
        return value
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ComfyVideoError("ComfyUI host must be localhost or a private IP") from exc
    if address.is_unspecified or not (address.is_private or address.is_loopback):
        raise ComfyVideoError("ComfyUI host must be localhost or a private IP")
    return value


def validate_adult_request(*, prompt: str, subject_basis: str) -> None:
    if subject_basis not in _ALLOWED_SUBJECT_BASES:
        raise ComfyVideoError(
            "adult profile requires --subject-basis fictional_adults or licensed_adults"
        )
    for pattern in _DISALLOWED_MINOR_SIGNALS:
        if pattern.search(prompt):
            raise ComfyVideoError("adult request rejected: minor or young-looking signal")


def _node(class_type: str, title: str, **inputs: Any) -> dict[str, Any]:
    return {"inputs": inputs, "class_type": class_type, "_meta": {"title": title}}


def build_wan22_i2v_prompt(
    *,
    image_name: str,
    prompt: str,
    width: int,
    height: int,
    duration_sec: int,
    seed: int,
    turbo: bool,
    profile: Mapping[str, str] = WAN22_OFFICIAL_PROFILE,
    filename_prefix: str = "video/aifilm_wan22",
    negative_prompt: str = DEFAULT_NEGATIVE,
) -> dict[str, dict[str, Any]]:
    if not image_name or "/" in image_name or "\\" in image_name:
        raise ComfyVideoError("image_name must be a ComfyUI input basename")
    if width < 256 or height < 256 or width > 1280 or height > 1280:
        raise ComfyVideoError("Wan 2.2 dimensions must be between 256 and 1280")
    if width % 16 or height % 16:
        raise ComfyVideoError("Wan 2.2 dimensions must be divisible by 16")
    if duration_sec < 1 or duration_sec > 10:
        raise ComfyVideoError("duration must be 1..10 seconds")
    if not prompt.strip():
        raise ComfyVideoError("prompt cannot be empty")
    if ".." in filename_prefix or filename_prefix.startswith("/"):
        raise ComfyVideoError("unsafe filename prefix")
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", filename_prefix):
        raise ComfyVideoError("filename prefix contains unsupported characters")
    if profile.get("name") == WAN22_ADULT_PROFILE["name"] and turbo:
        raise ComfyVideoError("adult-motion turbo is not promoted; use quality mode")

    fps = 16
    length = duration_sec * fps + 1
    steps = 4 if turbo else 20
    split_step = 2 if turbo else 10
    cfg = 1.0 if turbo else 3.5

    high_source = "unet_high"
    low_source = "unet_low"
    graph: dict[str, dict[str, Any]] = {
        "load_image": _node("LoadImage", "Load Image", image=image_name),
        "unet_high": _node(
            "UNETLoader",
            "Load Wan 2.2 high-noise expert",
            unet_name=profile["high"],
            weight_dtype="default",
        ),
        "unet_low": _node(
            "UNETLoader",
            "Load Wan 2.2 low-noise expert",
            unet_name=profile["low"],
            weight_dtype="default",
        ),
        "clip": _node(
            "CLIPLoader",
            "Load Wan text encoder",
            clip_name=WAN22_TEXT_ENCODER,
            type="wan",
            device="default",
        ),
        "positive": _node(
            "CLIPTextEncode",
            "Positive prompt",
            text=prompt,
            clip=["clip", 0],
        ),
        "negative": _node(
            "CLIPTextEncode",
            "Negative prompt",
            text=negative_prompt,
            clip=["clip", 0],
        ),
        "vae": _node("VAELoader", "Load Wan VAE", vae_name=WAN22_VAE),
    }
    if turbo:
        graph["lora_high"] = _node(
            "LoraLoaderModelOnly",
            "Load high-noise Lightning LoRA",
            lora_name=profile["high_lora"],
            strength_model=1.0,
            model=["unet_high", 0],
        )
        graph["lora_low"] = _node(
            "LoraLoaderModelOnly",
            "Load low-noise Lightning LoRA",
            lora_name=profile["low_lora"],
            strength_model=1.0,
            model=["unet_low", 0],
        )
        high_source = "lora_high"
        low_source = "lora_low"

    graph.update(
        {
            "model_high": _node(
                "ModelSamplingSD3",
                "High-noise sampling",
                shift=5.0,
                model=[high_source, 0],
            ),
            "model_low": _node(
                "ModelSamplingSD3",
                "Low-noise sampling",
                shift=5.0,
                model=[low_source, 0],
            ),
            "wan_i2v": _node(
                "WanImageToVideo",
                "Wan 2.2 image to video",
                width=width,
                height=height,
                length=length,
                batch_size=1,
                positive=["positive", 0],
                negative=["negative", 0],
                vae=["vae", 0],
                start_image=["load_image", 0],
            ),
            "sampler_high": _node(
                "KSamplerAdvanced",
                "Wan high-noise pass",
                add_noise="enable",
                noise_seed=seed,
                steps=steps,
                cfg=cfg,
                sampler_name="euler",
                scheduler="simple",
                start_at_step=0,
                end_at_step=split_step,
                return_with_leftover_noise="enable",
                model=["model_high", 0],
                positive=["wan_i2v", 0],
                negative=["wan_i2v", 1],
                latent_image=["wan_i2v", 2],
            ),
            "sampler_low": _node(
                "KSamplerAdvanced",
                "Wan low-noise pass",
                add_noise="disable",
                noise_seed=0,
                steps=steps,
                cfg=cfg,
                sampler_name="euler",
                scheduler="simple",
                start_at_step=split_step,
                end_at_step=steps,
                return_with_leftover_noise="disable",
                model=["model_low", 0],
                positive=["wan_i2v", 0],
                negative=["wan_i2v", 1],
                latent_image=["sampler_high", 0],
            ),
            "decode": _node(
                "VAEDecode",
                "Decode video frames",
                samples=["sampler_low", 0],
                vae=["vae", 0],
            ),
            "video": _node(
                "CreateVideo",
                "Create video",
                fps=float(fps),
                images=["decode", 0],
            ),
            "save": _node(
                "SaveVideo",
                "Save video",
                filename_prefix=filename_prefix,
                format="auto",
                codec="auto",
                video=["video", 0],
            ),
        }
    )
    return graph


def _json_request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
    timeout: float = 15,
) -> Any:
    url = f"{normalize_base_url(base_url)}{path}"
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.HTTPError) as exc:
        raise ComfyVideoError(f"ComfyUI {path} failed: {exc}") from exc


def _model_list(base_url: str, folder: str) -> list[str]:
    data = _json_request(base_url, f"/models/{urllib.parse.quote(folder)}")
    return [str(item) for item in data] if isinstance(data, list) else []


def _prompt_ids(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    prompt_ids: list[str] = []
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) > 1:
            prompt_id = str(item[1] or "")
            if prompt_id:
                prompt_ids.append(prompt_id)
    return prompt_ids


def queue_status(base_url: str) -> dict[str, Any]:
    data = _json_request(base_url, "/queue")
    if not isinstance(data, dict):
        raise ComfyVideoError("ComfyUI /queue returned an invalid payload")
    running = _prompt_ids(data.get("queue_running"))
    pending = _prompt_ids(data.get("queue_pending"))
    return {
        "running": len(running),
        "pending": len(pending),
        "running_prompt_ids": running,
        "pending_prompt_ids": pending,
    }


def inventory(base_url: str) -> dict[str, Any]:
    system = _json_request(base_url, "/system_stats")
    features = _json_request(base_url, "/features")
    model_folders = _json_request(base_url, "/models")
    folders = (
        [str(folder) for folder in model_folders if str(folder) in _INVENTORY_MODEL_FOLDERS]
        if isinstance(model_folders, list)
        else []
    )
    model_counts = {folder: len(_model_list(base_url, folder)) for folder in folders}
    system_info = system.get("system") if isinstance(system, dict) else {}
    devices = system.get("devices") if isinstance(system, dict) else []
    return {
        "schema_version": 1,
        "kind": "comfy-lan-inventory",
        "ok": True,
        "base_url": normalize_base_url(base_url),
        "system": {
            "comfyui_version": (system_info or {}).get("comfyui_version"),
            "python_version": (system_info or {}).get("python_version"),
            "pytorch_version": (system_info or {}).get("pytorch_version"),
            "ram_total": (system_info or {}).get("ram_total"),
            "ram_free": (system_info or {}).get("ram_free"),
        },
        "devices": [
            {
                "name": item.get("name"),
                "type": item.get("type"),
                "vram_total": item.get("vram_total"),
                "vram_free": item.get("vram_free"),
            }
            for item in devices or []
            if isinstance(item, dict)
        ],
        "features": features if isinstance(features, dict) else {},
        "model_counts": model_counts,
        "queue": queue_status(base_url),
    }


def load_api_workflow(path: Path) -> dict[str, dict[str, Any]]:
    workflow_path = Path(path).expanduser().resolve()
    try:
        data = json.loads(workflow_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ComfyVideoError(f"cannot read workflow JSON: {exc}") from exc
    if not isinstance(data, dict) or "nodes" in data or "links" in data:
        raise ComfyVideoError("workflow must use ComfyUI API format, not save format")
    if not data:
        raise ComfyVideoError("workflow API graph cannot be empty")
    for node_id, node in data.items():
        if not isinstance(node_id, str) or not isinstance(node, dict):
            raise ComfyVideoError("workflow API graph has an invalid node")
        if not isinstance(node.get("class_type"), str) or not node["class_type"].strip():
            raise ComfyVideoError(f"workflow node {node_id} is missing class_type")
        if not isinstance(node.get("inputs"), dict):
            raise ComfyVideoError(f"workflow node {node_id} is missing inputs")
    return data


def apply_workflow_overrides(
    graph: Mapping[str, Any],
    overrides: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    updated = copy.deepcopy(dict(graph))
    for node_id, inputs in overrides.items():
        node = updated.get(str(node_id))
        if not isinstance(node, dict):
            raise ComfyVideoError(f"workflow override references unknown node {node_id}")
        if not isinstance(inputs, Mapping):
            raise ComfyVideoError(f"workflow overrides for node {node_id} must be an object")
        node_inputs = node.get("inputs")
        if not isinstance(node_inputs, dict):
            raise ComfyVideoError(f"workflow node {node_id} has invalid inputs")
        for input_name, value in inputs.items():
            if input_name not in node_inputs:
                raise ComfyVideoError(
                    f"workflow override references unknown input {node_id}.{input_name}"
                )
            node_inputs[str(input_name)] = value
    return updated


def workflow_sha256(graph: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        graph,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def assert_local_only_workflow(base_url: str, graph: Mapping[str, Any]) -> None:
    class_types = sorted(
        {
            str(node.get("class_type"))
            for node in graph.values()
            if isinstance(node, Mapping) and node.get("class_type")
        }
    )
    for class_type in class_types:
        data = _json_request(
            base_url,
            f"/object_info/{urllib.parse.quote(class_type, safe='')}",
        )
        info = data.get(class_type, data) if isinstance(data, dict) else {}
        category = str((info or {}).get("category") or "").lower()
        if bool((info or {}).get("api_node")) or category.startswith("api node"):
            raise ComfyVideoError(
                f"workflow contains external API node {class_type}; "
                "explicit external-provider approval is required"
            )


def probe(base_url: str) -> dict[str, Any]:
    system = _json_request(base_url, "/system_stats")
    diffusion = _model_list(base_url, "diffusion_models")
    loras = _model_list(base_url, "loras")
    text_encoders = _model_list(base_url, "text_encoders")
    vaes = _model_list(base_url, "vae")
    devices = system.get("devices") or []
    required_official = {
        WAN22_OFFICIAL_PROFILE["high"],
        WAN22_OFFICIAL_PROFILE["low"],
        WAN22_TEXT_ENCODER,
        WAN22_VAE,
    }
    installed = set(diffusion) | set(text_encoders) | set(vaes)
    adult_pair = {WAN22_ADULT_PROFILE["high"], WAN22_ADULT_PROFILE["low"]}
    return {
        "schema_version": 1,
        "kind": "comfy-video-capability",
        "ok": required_official.issubset(installed),
        "base_url": normalize_base_url(base_url),
        "comfyui_version": (system.get("system") or {}).get("comfyui_version"),
        "devices": [
            {
                "name": item.get("name"),
                "vram_total": item.get("vram_total"),
                "vram_free": item.get("vram_free"),
            }
            for item in devices
        ],
        "profiles": {
            "official": required_official.issubset(installed),
            "official_turbo": {
                WAN22_OFFICIAL_PROFILE["high_lora"],
                WAN22_OFFICIAL_PROFILE["low_lora"],
            }.issubset(set(loras)),
            "adult_motion": required_official.issubset(installed),
        },
        "models": {
            "official": [WAN22_OFFICIAL_PROFILE["high"], WAN22_OFFICIAL_PROFILE["low"]],
            "adult_motion": [WAN22_ADULT_PROFILE["high"], WAN22_ADULT_PROFILE["low"]],
        },
        "experimental_adult_assets": {
            "merged_pair_present": adult_pair.issubset(set(diffusion)),
            "merged_pair_load_verified": False,
            "act_lora_present": "wan_cumshot_i2v.safetensors" in set(loras),
            "act_lora_promoted": False,
        },
    }


def upload_image(base_url: str, image_path: Path) -> dict[str, str]:
    path = Path(image_path).expanduser().resolve()
    if not path.is_file():
        raise ComfyVideoError(f"input image not found: {path}")
    if (
        '"' in path.name
        or "\r" in path.name
        or "\n" in path.name
        or any(ord(char) < 32 for char in path.name)
    ):
        raise ComfyVideoError("unsafe upload filename")
    boundary = f"aifilm-{secrets.token_hex(12)}"
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    content = path.read_bytes()
    parts = [
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        content,
        (
            f"\r\n--{boundary}\r\n"
            'Content-Disposition: form-data; name="type"\r\n\r\n'
            "input\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
            "false\r\n"
            f"--{boundary}--\r\n"
        ).encode(),
    ]
    body = b"".join(parts)
    request = urllib.request.Request(
        f"{normalize_base_url(base_url)}/upload/image",
        data=body,
        headers={
            "Accept": "application/json",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with _OPENER.open(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.HTTPError) as exc:
        raise ComfyVideoError(f"ComfyUI image upload failed: {exc}") from exc
    return {
        "name": str(data["name"]),
        "subfolder": str(data.get("subfolder") or ""),
        "type": str(data.get("type") or "input"),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def submit(
    base_url: str,
    graph: Mapping[str, Any],
    *,
    client_id: str | None = None,
) -> str:
    resolved_client_id = client_id or f"aifilm-{secrets.token_hex(8)}"
    data = _json_request(
        base_url,
        "/prompt",
        method="POST",
        payload={"client_id": resolved_client_id, "prompt": graph},
        timeout=30,
    )
    prompt_id = str(data.get("prompt_id") or "")
    if not prompt_id:
        raise ComfyVideoError(f"ComfyUI did not return prompt_id: {data}")
    return prompt_id


def _wait_for_completion_ws(
    base_url: str,
    prompt_id: str,
    *,
    client_id: str,
    timeout_sec: float,
) -> None:
    try:
        import websocket
    except ImportError as exc:  # pragma: no cover - depends on optional runtime package
        raise _WebSocketUnavailable("websocket-client is not installed") from exc

    parsed = urllib.parse.urlsplit(normalize_base_url(base_url))
    scheme = "wss" if parsed.scheme == "https" else "ws"
    websocket_url = urllib.parse.urlunsplit(
        (scheme, parsed.netloc, "/ws", f"clientId={urllib.parse.quote(client_id)}", "")
    )
    deadline = time.monotonic() + timeout_sec
    ws = None
    try:
        ws = websocket.create_connection(
            websocket_url,
            timeout=min(5.0, max(timeout_sec, 0.1)),
            suppress_origin=True,
        )
        while time.monotonic() < deadline:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                history = _json_request(
                    base_url,
                    f"/history/{urllib.parse.quote(prompt_id)}",
                )
                record = history.get(prompt_id) if isinstance(history, dict) else None
                if record and _completed_result(prompt_id, record) is not None:
                    return
                continue
            if not isinstance(raw, str):
                continue
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            data = message.get("data") or {}
            message_prompt_id = str(data.get("prompt_id") or "")
            if message.get("type") == "execution_error" and message_prompt_id == prompt_id:
                raise ComfyVideoError(
                    f"ComfyUI execution failed at node {data.get('node_id') or 'unknown'}"
                )
            if (
                message.get("type") == "executing"
                and message_prompt_id == prompt_id
                and data.get("node") is None
            ):
                return
    except ComfyVideoError:
        raise
    except Exception as exc:
        raise _WebSocketUnavailable(str(exc)) from exc
    finally:
        if ws is not None:
            ws.close()


def _completed_result(prompt_id: str, record: Mapping[str, Any]) -> dict[str, Any] | None:
    status = record.get("status") or {}
    if not status.get("completed"):
        return None
    if status.get("status_str") != "success":
        raise ComfyVideoError(f"ComfyUI generation failed: {status.get('status_str')}")
    artifacts: list[dict[str, str]] = []
    for output in (record.get("outputs") or {}).values():
        if not isinstance(output, Mapping):
            continue
        for value in output.values():
            if not isinstance(value, list):
                continue
            for item in value:
                if not isinstance(item, dict) or not item.get("filename"):
                    continue
                artifacts.append(
                    {
                        "filename": str(item["filename"]),
                        "subfolder": str(item.get("subfolder") or ""),
                        "type": str(item.get("type") or "output"),
                    }
                )
    for artifact in artifacts:
        if Path(artifact["filename"]).suffix.lower() in {".mp4", ".webm", ".mov", ".mkv"}:
            return {"prompt_id": prompt_id, **artifact, "artifacts": artifacts}
    if artifacts:
        return {"prompt_id": prompt_id, **artifacts[0], "artifacts": artifacts}
    raise ComfyVideoError("ComfyUI completed without a downloadable output")


def _raise_for_execution_error(record: Mapping[str, Any]) -> None:
    status = record.get("status") or {}
    if not isinstance(status, Mapping):
        return
    status_str = str(status.get("status_str") or "").lower()
    messages = status.get("messages") or []
    error_details: Mapping[str, Any] = {}
    for message in messages:
        if (
            isinstance(message, list)
            and len(message) == 2
            and message[0] == "execution_error"
            and isinstance(message[1], Mapping)
        ):
            error_details = message[1]
            break
    if status_str not in {"error", "failed"} and not error_details:
        return
    node_id = str(error_details.get("node_id") or "unknown node")
    detail = str(
        error_details.get("exception_message")
        or error_details.get("exception_type")
        or status_str
        or "unknown error"
    )
    raise ComfyVideoError(f"ComfyUI generation failed at {node_id}: {detail}")


def wait_for_result(
    base_url: str,
    prompt_id: str,
    *,
    client_id: str | None = None,
    timeout_sec: int = 1200,
    poll_sec: float = 2,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_sec
    initial = _json_request(base_url, f"/history/{urllib.parse.quote(prompt_id)}")
    initial_record = initial.get(prompt_id) if isinstance(initial, dict) else None
    if initial_record:
        _raise_for_execution_error(initial_record)
        initial_result = _completed_result(prompt_id, initial_record)
        if initial_result is not None:
            return initial_result
    if client_id:
        with contextlib.suppress(_WebSocketUnavailable):
            _wait_for_completion_ws(
                base_url,
                prompt_id,
                client_id=client_id,
                timeout_sec=max(0.1, deadline - time.monotonic()),
            )
    while time.monotonic() < deadline:
        data = _json_request(base_url, f"/history/{urllib.parse.quote(prompt_id)}")
        record = data.get(prompt_id) if isinstance(data, dict) else None
        if not record:
            time.sleep(poll_sec)
            continue
        _raise_for_execution_error(record)
        result = _completed_result(prompt_id, record)
        if result is not None:
            return result
        time.sleep(poll_sec)
    raise ComfyVideoError(f"ComfyUI generation timed out after {timeout_sec}s")


def cancel_prompt(base_url: str, prompt_id: str) -> dict[str, Any]:
    status = queue_status(base_url)
    if prompt_id in status["pending_prompt_ids"]:
        _json_request(
            base_url,
            "/queue",
            method="POST",
            payload={"delete": [prompt_id]},
        )
        return {"ok": True, "prompt_id": prompt_id, "action": "delete_pending"}
    if prompt_id in status["running_prompt_ids"]:
        if len(status["running_prompt_ids"]) != 1:
            raise ComfyVideoError("refusing global interrupt while multiple prompts are running")
        _json_request(base_url, "/interrupt", method="POST", payload={})
        return {"ok": True, "prompt_id": prompt_id, "action": "interrupt"}
    raise ComfyVideoError(f"prompt {prompt_id} is not present in the active queue")


def free_memory(base_url: str) -> dict[str, Any]:
    _json_request(
        base_url,
        "/free",
        method="POST",
        payload={"unload_models": True, "free_memory": True},
    )
    return {"ok": True, "action": "free_memory"}


def download_result(base_url: str, result: Mapping[str, str], out: Path) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "filename": result["filename"],
            "subfolder": result.get("subfolder", ""),
            "type": result.get("type", "output"),
        }
    )
    request = urllib.request.Request(
        f"{normalize_base_url(base_url)}/view?{params}",
        headers={"Accept": "*/*"},
    )
    try:
        with _OPENER.open(request, timeout=180) as response:
            content = response.read()
    except (OSError, urllib.error.HTTPError) as exc:
        raise ComfyVideoError(f"ComfyUI artifact download failed: {exc}") from exc
    if not content:
        raise ComfyVideoError("downloaded artifact is empty")
    if (
        Path(result["filename"]).suffix.lower() in {".mp4", ".webm", ".mov", ".mkv"}
        and len(content) < 10_000
    ):
        raise ComfyVideoError("downloaded video is unexpectedly small")
    output = Path(out).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    return {
        "path": str(output),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def generate(
    *,
    base_url: str,
    image: Path,
    prompt: str,
    out: Path,
    width: int,
    height: int,
    duration_sec: int,
    seed: int,
    turbo: bool,
    profile: Mapping[str, str],
    subject_basis: str,
    timeout_sec: int = 1800,
) -> dict[str, Any]:
    if profile.get("name") == WAN22_ADULT_PROFILE["name"]:
        validate_adult_request(prompt=prompt, subject_basis=subject_basis)
    capability = probe(base_url)
    profile_key = "adult_motion" if profile.get("name") == "adult-motion" else "official"
    if not capability["profiles"].get(profile_key):
        raise ComfyVideoError(f"required Wan profile is not installed: {profile_key}")
    uploaded = upload_image(base_url, image)
    graph = build_wan22_i2v_prompt(
        image_name=uploaded["name"],
        prompt=prompt,
        width=width,
        height=height,
        duration_sec=duration_sec,
        seed=seed,
        turbo=turbo,
        profile=profile,
    )
    client_id = f"aifilm-{secrets.token_hex(8)}"
    prompt_id = submit(base_url, graph, client_id=client_id)
    result = wait_for_result(
        base_url,
        prompt_id,
        client_id=client_id,
        timeout_sec=timeout_sec,
    )
    downloaded = download_result(base_url, result, out)
    return {
        "schema_version": 1,
        "kind": "local-wan22-generation",
        "ok": True,
        "provider": "comfy-wan22",
        "profile": profile["name"],
        "prompt_id": prompt_id,
        "input_sha256": hashlib.sha256(Path(image).read_bytes()).hexdigest(),
        "output": downloaded,
        "models": [profile["high"], profile["low"]],
        "turbo": turbo,
        "width": width,
        "height": height,
        "duration_sec": duration_sec,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Private RTX 5090 ComfyUI video client")
    sub = parser.add_subparsers(dest="command", required=True)
    probe_cmd = sub.add_parser("probe")
    probe_cmd.add_argument("--base-url", required=True)

    generate_cmd = sub.add_parser("generate")
    generate_cmd.add_argument("--base-url", required=True)
    generate_cmd.add_argument("--image", type=Path, required=True)
    generate_cmd.add_argument("--prompt", required=True)
    generate_cmd.add_argument("--out", type=Path, required=True)
    generate_cmd.add_argument("--width", type=int, default=480)
    generate_cmd.add_argument("--height", type=int, default=704)
    generate_cmd.add_argument("--duration", type=int, default=3)
    generate_cmd.add_argument("--timeout", type=int, default=1800)
    generate_cmd.add_argument("--seed", type=int, default=123456)
    generate_cmd.add_argument("--profile", choices=("official", "adult-motion"), default="official")
    generate_cmd.add_argument(
        "--subject-basis", choices=sorted(_ALLOWED_SUBJECT_BASES), default=None
    )
    generate_cmd.add_argument("--turbo", action="store_true")
    generate_cmd.add_argument(
        "--receipt",
        type=Path,
        default=None,
        help="Defaults to <output>.receipt.json",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "probe":
        report = probe(args.base_url)
    else:
        profile = WAN22_ADULT_PROFILE if args.profile == "adult-motion" else WAN22_OFFICIAL_PROFILE
        report = generate(
            base_url=args.base_url,
            image=args.image,
            prompt=args.prompt,
            out=args.out,
            width=args.width,
            height=args.height,
            duration_sec=args.duration,
            seed=args.seed,
            turbo=args.turbo,
            profile=profile,
            subject_basis=args.subject_basis or "",
            timeout_sec=args.timeout,
        )
        receipt_path = args.receipt or args.out.with_suffix(args.out.suffix + ".receipt.json")
        report["receipt_path"] = str(Path(receipt_path).expanduser().resolve())
        write_json(Path(receipt_path).expanduser().resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
