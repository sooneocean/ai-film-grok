#!/usr/bin/env python3
"""Private ComfyUI helpers for the user's RTX 5090 node.

The historical local Wan 2.2 I2V submitter is retained only for receipt and
workflow inspection compatibility. Generation is retired and fails closed.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shlex
import subprocess
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows is the remote executor, not orchestrator
    fcntl = None  # type: ignore[assignment]


class ComfyVideoError(RuntimeError):
    pass


class _WebSocketUnavailable(RuntimeError):
    pass


GIB = 1024**3
DEFAULT_MIN_FREE_RAM_BYTES = 12 * GIB
DEFAULT_MIN_FREE_VRAM_BYTES = 24 * GIB
_SUBMISSION_LOCK_WAIT_SEC = 5.0
_SSH_TARGET = re.compile(r"^[A-Za-z0-9_.\\-]+@[A-Za-z0-9.:-]+$")
WAN22_I2V_RETIRED = "WAN22_I2V_RETIRED: local Wan 2.2 I2V cannot be submitted"


# Historical profile name stubs (imports/receipts only — generation is retired).
WAN22_OFFICIAL_PROFILE: dict[str, Any] = {"name": "official"}
WAN22_ADULT_PROFILE: dict[str, Any] = {"name": "adult-motion"}
WAN22_ADULT_ACTION_EXPERIMENTAL_PROFILE: dict[str, Any] = {"name": "adult-action-experimental"}
WAN22_GENERAL_ADULT_EXPERIMENTAL_PROFILE: dict[str, Any] = {"name": "adult-general-experimental"}


def select_wan22_weapon(
    *,
    intent: str = "general",
    stage: str = "production",
    allow_experimental: bool = False,
) -> dict[str, Any]:
    """Retired — local Wan 2.2 weapon routing is gone (H3 owns motion)."""
    del intent, stage, allow_experimental
    raise ComfyVideoError(WAN22_I2V_RETIRED)


def resolve_wan22_profile(
    profile_name: str,
    *,
    intent: str = "general",
    stage: str = "production",
    allow_experimental: bool = False,
) -> Mapping[str, Any]:
    """Retired — profile resolution fails closed."""
    del profile_name, intent, stage, allow_experimental
    raise ComfyVideoError(WAN22_I2V_RETIRED)


_DISALLOWED_MINOR_SIGNALS = (
    re.compile(r"\bunderage\b", re.I),
    re.compile(r"\bminor\b", re.I),
    re.compile(r"\bschool[\s-]?girl\b", re.I),
    re.compile(r"\bschool[\s-]?boy\b", re.I),
    re.compile(r"\bteen(?:age|ager|aged|[\s-]?looking)?\b", re.I),
    re.compile(r"\bloli(?:con)?\b", re.I),
    re.compile(r"\bshota(?:con)?\b", re.I),
    re.compile(r"\bchild(?:ren)?\b", re.I),
    re.compile(r"\byoung[\s-]+(?:girl|boy)\b", re.I),
    re.compile(
        r"(?<!\d)(?:[0-9]|1[0-7])\s*(?:[-‐‑–—]\s*)?"
        r"(?:years?[-\s]*old|y\s*/?\s*o|歲|岁|歳|才)\b",
        re.I,
    ),
    re.compile(r"未成年|未滿\s*18|未满\s*18"),
    re.compile(r"女子高生|男子高生|高校生|中学生|中學生|小学生|小學生"),
    re.compile(r"高中生|初中生|國中生|国中生"),
    re.compile(r"少女|少年|兒童|儿童|小孩|孩童"),
)
_ALLOWED_SUBJECT_BASES = frozenset({"fictional_adults", "licensed_adults"})
_ALLOWED_COMFY_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
)
_MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
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
    if not (
        address.is_loopback
        or any(
            address.version == network.version and address in network
            for network in _ALLOWED_COMFY_NETWORKS
        )
    ):
        raise ComfyVideoError("ComfyUI host must be localhost or a private IP")
    if parsed.scheme == "http" and not address.is_loopback:
        raise ComfyVideoError("private-LAN ComfyUI requires HTTPS or a loopback SSH tunnel")
    return value


def validate_adult_request(*, prompt: str, subject_basis: str) -> None:
    if subject_basis not in _ALLOWED_SUBJECT_BASES:
        raise ComfyVideoError(
            "adult profile requires --subject-basis fictional_adults or licensed_adults"
        )
    normalized_prompt = unicodedata.normalize("NFKC", prompt).casefold()
    for pattern in _DISALLOWED_MINOR_SIGNALS:
        if pattern.search(normalized_prompt):
            raise ComfyVideoError("adult request rejected: minor or young-looking signal")


def build_wan22_i2v_prompt(**_kwargs: Any) -> dict[str, dict[str, Any]]:
    """Retired — graph build fails closed (do not submit Wan I2V)."""
    raise ComfyVideoError(WAN22_I2V_RETIRED)


def _json_request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
    extra_headers: Mapping[str, str] | None = None,
    timeout: float = 15,
) -> Any:
    url = f"{normalize_base_url(base_url)}{path}"
    body = None
    headers = {"Accept": "application/json"}
    broker_token = str(os.environ.get("AIFILM_COMFY_BROKER_TOKEN") or "")
    if broker_token:
        if len(broker_token) < 32:
            raise ComfyVideoError("AIFILM_COMFY_BROKER_TOKEN must be at least 32 characters")
        headers["Authorization"] = f"Bearer {broker_token}"
    if extra_headers:
        headers.update(extra_headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except (OSError, ValueError, urllib.error.HTTPError) as exc:
        raise ComfyVideoError(f"ComfyUI {path} failed: {exc}") from exc


def _model_list(base_url: str, folder: str) -> list[str]:
    data = _json_request(base_url, f"/models/{urllib.parse.quote(folder)}")
    return [str(item) for item in data] if isinstance(data, list) else []


def _model_sha256(base_url: str, folder: str, filename: str) -> str:
    encoded = urllib.parse.quote(f"{folder}/{filename}", safe="")
    data = _json_request(base_url, f"/pysssss/metadata/{encoded}")
    candidates = (
        data.get("sha256"),
        data.get("hash"),
        data.get("pysssss.sha256"),
        (data.get("metadata") or {}).get("sha256")
        if isinstance(data.get("metadata"), Mapping)
        else None,
    )
    value = next((str(item).lower() for item in candidates if item), "")
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ComfyVideoError(f"ComfyUI metadata has no valid SHA-256 for {folder}/{filename}")
    return value


def _prompt_ids(items: object, *, queue_name: str) -> list[str]:
    if not isinstance(items, list):
        raise ComfyVideoError(f"ComfyUI /queue has invalid {queue_name} telemetry")
    prompt_ids: list[str] = []
    for item in items:
        if not isinstance(item, (list, tuple)) or len(item) <= 1:
            raise ComfyVideoError(f"ComfyUI /queue has malformed {queue_name} item")
        prompt_id = str(item[1] or "")
        if not prompt_id:
            raise ComfyVideoError(f"ComfyUI /queue has empty {queue_name} prompt id")
        prompt_ids.append(prompt_id)
    return prompt_ids


def queue_status(base_url: str) -> dict[str, Any]:
    data = _json_request(base_url, "/queue")
    if not isinstance(data, dict):
        raise ComfyVideoError("ComfyUI /queue returned an invalid payload")
    if "queue_running" not in data or "queue_pending" not in data:
        raise ComfyVideoError("ComfyUI /queue telemetry is incomplete")
    running = _prompt_ids(data["queue_running"], queue_name="running")
    pending = _prompt_ids(data["queue_pending"], queue_name="pending")
    return {
        "running": len(running),
        "pending": len(pending),
        "running_prompt_ids": running,
        "pending_prompt_ids": pending,
    }


def _driver_vram_probe(
    *,
    base_url: str,
    expected_hostname: str,
    expected_comfy_version: str,
    expected_python_version: str,
    expected_device_name: str,
    expected_vram_total: int | None,
) -> tuple[int | None, str | None]:
    """Read the configured private executor's physical free VRAM, if available."""
    # Configuration loading belongs to the CLI boundary. Re-loading config.env
    # here would mutate a caller's environment and make capacity checks depend
    # on unrelated local state (including test fixtures).
    if str(os.environ.get("AIFILM_COMFY_DRIVER_VRAM_FALLBACK") or "").strip() != "1":
        return None, None
    target = str(os.environ.get("AIFILM_COMFY_SSH_TARGET") or "").strip()
    key = str(os.environ.get("AIFILM_COMFY_SSH_KEY") or "").strip()
    known_hosts = str(os.environ.get("AIFILM_COMFY_SSH_KNOWN_HOSTS") or "").strip()
    hostkey_alias = str(os.environ.get("AIFILM_COMFY_SSH_HOSTKEY_ALIAS") or "").strip()
    if not all((target, key, known_hosts, hostkey_alias, expected_hostname)):
        return None, "driver VRAM fallback is enabled but SSH configuration is incomplete"
    if not _SSH_TARGET.fullmatch(target):
        return None, "driver VRAM fallback SSH target is invalid"
    parsed_base_url = urllib.parse.urlsplit(normalize_base_url(base_url))
    if parsed_base_url.scheme != "http" or parsed_base_url.hostname != "127.0.0.1":
        return None, "driver VRAM fallback requires a loopback SSH tunnel endpoint"
    local_port = parsed_base_url.port
    if local_port is None:
        return None, "driver VRAM fallback requires an explicit loopback SSH tunnel port"
    try:
        listener = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{local_port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        listener_pids = [line.strip() for line in listener.stdout.splitlines() if line.strip()]
        if listener.returncode != 0 or len(listener_pids) != 1 or not listener_pids[0].isdigit():
            return None, "driver VRAM fallback cannot verify the loopback SSH tunnel listener"
        tunnel = subprocess.run(
            ["ps", "-p", listener_pids[0], "-o", "command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, "driver VRAM fallback cannot inspect the loopback SSH tunnel"
    forward = f"127.0.0.1:{local_port}:127.0.0.1:8188"
    try:
        # Windows user targets legitimately contain a backslash.  POSIX shlex
        # would consume it and turn the destination comparison into a false
        # mismatch, so preserve the listener process's argv spelling.
        tunnel_argv = shlex.split(tunnel.stdout.strip(), posix=False)
    except ValueError:
        tunnel_argv = []
    has_forward = any(
        token == forward and index > 0 and tunnel_argv[index - 1] in {"-L", "-oLocalForward"}
        for index, token in enumerate(tunnel_argv)
    )
    has_hostkey_alias = (
        any(
            token == f"HostKeyAlias={hostkey_alias}"
            and index > 0
            and tunnel_argv[index - 1] == "-o"
            for index, token in enumerate(tunnel_argv)
        )
        or f"-oHostKeyAlias={hostkey_alias}" in tunnel_argv
    )
    if (
        tunnel.returncode != 0
        or not tunnel_argv
        or tunnel_argv[0] != "ssh"
        or not has_forward
        or tunnel_argv[-1] != target
        or not has_hostkey_alias
    ):
        return None, "driver VRAM fallback loopback endpoint is not the authenticated SSH tunnel"
    command = [
        "ssh",
        "-i",
        key,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        f"HostKeyAlias={hostkey_alias}",
        "--",
        target,
        (
            'powershell -NoProfile -Command "'
            "$stats=Invoke-RestMethod http://127.0.0.1:8188/system_stats; "
            "$gpu=@($stats.devices | Where-Object {$_.type -eq 'cuda'}); "
            "if($gpu.Count -ne 1){exit 2}; "
            "$free=(& nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits).Trim(); "
            "[PSCustomObject]@{hostname=$env:COMPUTERNAME; "
            "comfy_version=$stats.system.comfyui_version; python_version=$stats.system.python_version; "
            'gpu_name=$gpu[0].name; gpu_total=$gpu[0].vram_total; gpu_free_mib=$free}|ConvertTo-Json -Compress"'
        ),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None, "driver VRAM fallback SSH probe failed"
    values = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode != 0 or len(values) != 1:
        return None, "driver VRAM fallback SSH probe returned invalid data"
    try:
        identity = json.loads(values[0])
    except ValueError:
        return None, "driver VRAM fallback SSH probe returned invalid data"
    if not isinstance(identity, dict):
        return None, "driver VRAM fallback SSH probe returned invalid data"
    driver_name = str(identity.get("gpu_name") or "")
    raw_mib = str(identity.get("gpu_free_mib") or "")
    if (
        str(identity.get("hostname") or "").casefold() != expected_hostname.casefold()
        or str(identity.get("comfy_version") or "") != expected_comfy_version
        or str(identity.get("python_version") or "") != expected_python_version
        or identity.get("gpu_total") != expected_vram_total
    ):
        return None, "driver VRAM fallback executor does not match the ComfyUI endpoint"
    if not raw_mib.isdigit() or "rtx5090" not in re.sub(r"[^a-z0-9]", "", driver_name.lower()):
        return None, "driver VRAM fallback GPU identity is invalid"
    if "rtx5090" not in re.sub(r"[^a-z0-9]", "", expected_device_name.lower()):
        return None, "ComfyUI CUDA device does not match the configured driver GPU"
    return int(raw_mib) * 1024**2, None


def submission_capacity(base_url: str) -> dict[str, Any]:
    system = _json_request(base_url, "/system_stats")
    queue = queue_status(base_url)
    system_info = (
        system.get("system")
        if isinstance(system, dict) and isinstance(system.get("system"), Mapping)
        else {}
    )
    devices = (
        system.get("devices")
        if isinstance(system, dict) and isinstance(system.get("devices"), list)
        else []
    )
    ram_free = (system_info or {}).get("ram_free")
    cuda_devices = [
        item
        for item in devices or []
        if isinstance(item, dict) and str(item.get("type") or "").lower() == "cuda"
    ]
    selected_device = cuda_devices[0] if len(cuda_devices) == 1 else None
    reported_vram = selected_device.get("vram_free") if selected_device else None
    comfy_vram_free = reported_vram if type(reported_vram) is int and reported_vram >= 0 else None
    driver_vram_free, driver_vram_error = (
        _driver_vram_probe(
            base_url=base_url,
            expected_hostname=str(os.environ.get("AIFILM_COMFY_SSH_EXPECTED_HOSTNAME") or ""),
            expected_comfy_version=str((system_info or {}).get("comfyui_version") or ""),
            expected_python_version=str((system_info or {}).get("python_version") or ""),
            expected_device_name=str(selected_device.get("name") or ""),
            expected_vram_total=selected_device.get("vram_total"),
        )
        if selected_device
        else (None, None)
    )
    vram_free = driver_vram_free if driver_vram_free is not None else comfy_vram_free
    blockers: list[dict[str, str]] = []
    if type(ram_free) is not int or ram_free < 0:
        blockers.append(
            {
                "code": "RESOURCE_METRICS_UNAVAILABLE",
                "message": "ComfyUI did not report valid free system memory",
            }
        )
    elif ram_free < DEFAULT_MIN_FREE_RAM_BYTES:
        blockers.append(
            {
                "code": "RAM_BELOW_FLOOR",
                "message": "free system memory is below the 12 GiB submission floor",
            }
        )
    if len(cuda_devices) != 1 or vram_free is None:
        blockers.append(
            {
                "code": "RESOURCE_METRICS_UNAVAILABLE",
                "message": (
                    "ComfyUI must report exactly one CUDA execution device "
                    "with valid free GPU memory"
                ),
            }
        )
    elif vram_free < DEFAULT_MIN_FREE_VRAM_BYTES:
        blockers.append(
            {
                "code": "VRAM_BELOW_FLOOR",
                "message": "free GPU memory is below the 24 GiB submission floor",
            }
        )
    # Driver VRAM is preferred when available, but a failed SSH nvidia-smi probe
    # must not block submission when ComfyUI already reported valid free VRAM.
    if driver_vram_error and driver_vram_free is None and comfy_vram_free is None:
        blockers.append(
            {
                "code": "RESOURCE_METRICS_UNAVAILABLE",
                "message": driver_vram_error,
            }
        )
    if queue["running"] or queue["pending"]:
        blockers.append(
            {
                "code": "COMFY_QUEUE_BUSY",
                "message": "another ComfyUI prompt is running or pending",
            }
        )
    return {
        "schema_version": 1,
        "kind": "comfy-submission-capacity",
        "ok": not blockers,
        "status": "ready" if not blockers else "blocked",
        "base_url": normalize_base_url(base_url),
        "floors": {
            "ram_free_bytes": DEFAULT_MIN_FREE_RAM_BYTES,
            "vram_free_bytes": DEFAULT_MIN_FREE_VRAM_BYTES,
            "queue_must_be_idle": True,
        },
        "observed": {
            "ram_free_bytes": ram_free if type(ram_free) is int else None,
            "device": {
                "name": selected_device.get("name"),
                "vram_total_bytes": selected_device.get("vram_total"),
                "vram_free_bytes": vram_free,
                "comfy_vram_free_bytes": comfy_vram_free,
                "driver_vram_free_bytes": driver_vram_free,
                "driver_vram_probe_error": driver_vram_error,
                "vram_source": "nvidia-smi-via-ssh" if driver_vram_free is not None else "comfyui",
            }
            if selected_device
            else None,
            "queue": {
                "running": queue["running"],
                "pending": queue["pending"],
            },
        },
        "blockers": blockers,
    }


def assert_submission_capacity(base_url: str) -> dict[str, Any]:
    report = submission_capacity(base_url)
    if not report["ok"]:
        codes = ",".join(item["code"] for item in report["blockers"])
        raise ComfyVideoError(f"ComfyUI submission blocked by resource tower: {codes}")
    return report


@contextlib.contextmanager
def _submission_admission_lock(base_url: str):
    if fcntl is None:
        raise ComfyVideoError("ComfyUI submission requires the POSIX Mac orchestrator")
    lock_key = hashlib.sha256(normalize_base_url(base_url).encode("utf-8")).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"aifilm-comfy-submit-{lock_key}.lock"
    deadline = time.monotonic() + _SUBMISSION_LOCK_WAIT_SEC
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError as exc:
        raise ComfyVideoError("ComfyUI submission admission lock failed") from exc
    locked = False
    while not locked:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(descriptor)
                raise ComfyVideoError("ComfyUI submission blocked: local admission lock is busy")
            time.sleep(0.05)
        except OSError as exc:
            os.close(descriptor)
            raise ComfyVideoError("ComfyUI submission admission lock failed") from exc
    try:
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


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
            current = node_inputs[input_name]
            compatible = (
                (type(current) is bool and type(value) is bool)
                or (type(current) is int and type(value) is int)
                or (type(current) is float and type(value) in {int, float})
                or (isinstance(current, str) and isinstance(value, str))
                or (isinstance(current, list) and isinstance(value, list))
                or (isinstance(current, Mapping) and isinstance(value, Mapping))
            )
            if current is None or not compatible:
                raise ComfyVideoError(f"workflow override type mismatch for {node_id}.{input_name}")
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
        if not isinstance(info, Mapping) or not info:
            raise ComfyVideoError(f"workflow node metadata unavailable: {class_type}")
        category = str((info or {}).get("category") or "").lower()
        input_info = (info or {}).get("input") if isinstance(info, Mapping) else {}
        declared_inputs: set[str] = set()
        if isinstance(input_info, Mapping):
            for section in ("required", "optional", "hidden"):
                values = input_info.get(section)
                if isinstance(values, Mapping):
                    declared_inputs.update(str(name).lower() for name in values)
        external_name = re.search(
            r"(?:openai|anthropic|gemini|replicate|falai|fal_ai|stabilityai|"
            r"bytedance|kling|runway|luma|cloud)",
            class_type,
            re.I,
        )
        credentialed_endpoint = bool(
            {"api_key", "apikey", "access_token", "secret_key"} & declared_inputs
            and {"endpoint", "base_url", "api_url", "model_name"} & declared_inputs
        )
        if (
            bool((info or {}).get("api_node"))
            or category.startswith("api node")
            or external_name
            or credentialed_endpoint
        ):
            raise ComfyVideoError(
                f"workflow contains external API node {class_type}; "
                "explicit external-provider approval is required"
            )
        python_module = str(info.get("python_module") or "")
        if python_module != "nodes" and not python_module.startswith("comfy_extras."):
            raise ComfyVideoError(
                f"workflow contains untrusted custom node {class_type} "
                f"from {python_module or 'unknown module'}; explicit approval is required"
            )


def probe(base_url: str) -> dict[str, Any]:
    """ComfyUI connectivity + device snapshot.

    Wan 2.2 weight inventory is no longer a readiness gate — motion primary is
    MiniMax H3 (see comfy_armory). ``ok`` means the node answered /system_stats.
    """
    system = _json_request(base_url, "/system_stats")
    devices = system.get("devices") or []
    return {
        "schema_version": 2,
        "kind": "comfy-video-capability",
        "ok": True,
        "wan22_retired": True,
        "wan22_generation": "retired",
        "base_url": normalize_base_url(base_url),
        "comfyui_version": (system.get("system") or {}).get("comfyui_version"),
        "devices": [
            {
                "name": item.get("name"),
                "vram_total": item.get("vram_total"),
                "vram_free": item.get("vram_free"),
            }
            for item in devices
            if isinstance(item, dict)
        ],
        "profiles": {
            "official": False,
            "official_turbo": False,
            "adult_motion": False,
            "adult_action_experimental": False,
            "adult_general_experimental": False,
        },
        "profile_lora_sha256": {"adult_general_experimental": {}},
        "models": {"official": [], "adult_motion": []},
        "experimental_adult_assets": {
            "merged_pair_present": False,
            "merged_pair_load_verified": False,
            "act_lora_present": False,
            "act_lora_promoted": False,
            "verified_wan22_pair_present": False,
            "verified_wan22_pair_promoted": False,
            "general_wan22_pair_present": False,
            "general_wan22_pair_hashes_verified": False,
            "general_wan22_pair_promoted": False,
        },
    }


def _safe_comfy_upload_filename(path: Path, content: bytes) -> str:
    """Stable ASCII name for Comfy input slot (no spaces/parens from collision renames).

    ComfyUI renames duplicate uploads to ``name (1).ext`` which fails armory
    ``_SAFE_PREFIX`` and breaks H3 continue-handoff chains (C1 · 2026-08-06).
    """
    ext = path.suffix.lower() if path.suffix else ".png"
    if ext not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        ext = ".png"
    digest = hashlib.sha256(content).hexdigest()[:16]
    return f"aifilm_{digest}{ext}"


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
    content = path.read_bytes()
    upload_name = _safe_comfy_upload_filename(path, content)
    content_type = mimetypes.guess_type(upload_name)[0] or "application/octet-stream"
    parts = [
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{upload_name}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        content,
        (
            f"\r\n--{boundary}\r\n"
            'Content-Disposition: form-data; name="type"\r\n\r\n'
            "input\r\n"
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
            "true\r\n"
            f"--{boundary}--\r\n"
        ).encode(),
    ]
    body = b"".join(parts)
    headers = {
        "Accept": "application/json",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    broker_token = str(os.environ.get("AIFILM_COMFY_BROKER_TOKEN") or "")
    if broker_token:
        if len(broker_token) < 32:
            raise ComfyVideoError("AIFILM_COMFY_BROKER_TOKEN must be at least 32 characters")
        headers["Authorization"] = f"Bearer {broker_token}"
    request = urllib.request.Request(
        f"{normalize_base_url(base_url)}/upload/image",
        data=body,
        headers=headers,
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
    weapon_id: str | None = None,
    allow_queue: bool = False,
) -> str:
    with _submission_admission_lock(base_url):
        if allow_queue:
            report = submission_capacity(base_url)
            codes = {str(item.get("code") or "") for item in report["blockers"]}
            queue = report["observed"]["queue"]
            if not queue["running"] and not queue["pending"]:
                raise ComfyVideoError("queue submission requires an occupied ComfyUI queue")
            if not codes or not codes <= {
                "RAM_BELOW_FLOOR",
                "VRAM_BELOW_FLOOR",
                "COMFY_QUEUE_BUSY",
            }:
                raise ComfyVideoError("queue submission blocked by a non-capacity health error")
        else:
            assert_submission_capacity(base_url)
        resolved_client_id = client_id or f"aifilm-{secrets.token_hex(8)}"
        data = _json_request(
            base_url,
            "/prompt",
            method="POST",
            payload={"client_id": resolved_client_id, "prompt": graph},
            extra_headers=(
                {
                    "X-AIFilm-Weapon-ID": weapon_id,
                    "X-AIFilm-Workflow-SHA256": workflow_sha256(graph),
                }
                if weapon_id
                else None
            ),
            timeout=30,
        )
    prompt_id = str(data.get("prompt_id") or "")
    if not prompt_id:
        raise ComfyVideoError("ComfyUI did not return a prompt id")
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
            redirect_limit=0,
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
                if record:
                    _raise_for_execution_error(record)
                    if _completed_result(prompt_id, record) is not None:
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
    detail = str(error_details.get("exception_type") or status_str or "unknown error")
    detail = re.sub(r"[^A-Za-z0-9_. -]", "_", detail)[:80]
    node_id = re.sub(r"[^A-Za-z0-9_.-]", "_", node_id)[:80]
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
        raise ComfyVideoError(
            "ComfyUI /interrupt is global and not target-safe; "
            "refusing to interrupt a running prompt"
        )
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
    headers = {"Accept": "*/*"}
    broker_token = str(os.environ.get("AIFILM_COMFY_BROKER_TOKEN") or "")
    if broker_token:
        if len(broker_token) < 32:
            raise ComfyVideoError("AIFILM_COMFY_BROKER_TOKEN must be at least 32 characters")
        headers["Authorization"] = f"Bearer {broker_token}"
    request = urllib.request.Request(
        f"{normalize_base_url(base_url)}/view?{params}",
        headers=headers,
    )
    output = Path(out).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f".{output.name}.{secrets.token_hex(8)}.partial")
    digest = hashlib.sha256()
    total = 0
    try:
        with _OPENER.open(request, timeout=180) as response:
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > _MAX_ARTIFACT_BYTES:
                raise ComfyVideoError("ComfyUI artifact exceeds size limit")
            with partial.open("xb") as handle:
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > _MAX_ARTIFACT_BYTES:
                        raise ComfyVideoError("ComfyUI artifact exceeds size limit")
                    digest.update(chunk)
                    handle.write(chunk)
        if total == 0:
            raise ComfyVideoError("downloaded artifact is empty")
        if (
            Path(result["filename"]).suffix.lower() in {".mp4", ".webm", ".mov", ".mkv"}
            and total < 10_000
        ):
            raise ComfyVideoError("downloaded video is unexpectedly small")
        partial.replace(output)
    except (OSError, ValueError, urllib.error.HTTPError) as exc:
        partial.unlink(missing_ok=True)
        raise ComfyVideoError("ComfyUI artifact download failed") from exc
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return {
        "path": str(output),
        "bytes": total,
        "sha256": digest.hexdigest(),
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
    profile: Mapping[str, Any],
    subject_basis: str,
    timeout_sec: int = 1800,
) -> dict[str, Any]:
    raise ComfyVideoError(WAN22_I2V_RETIRED)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Private RTX 5090 ComfyUI helpers; Wan 2.2 generation is retired"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    probe_cmd = sub.add_parser("probe")
    probe_cmd.add_argument("--base-url", required=True)

    generate_cmd = sub.add_parser("generate", help="Retired; rejects without contacting ComfyUI")
    # Accept leftover CLI flags so old wrappers still parse, then fail closed in main.
    generate_cmd.add_argument("--base-url", required=True)
    generate_cmd.add_argument("--image", type=Path, default=None)
    generate_cmd.add_argument("--prompt", default="")
    generate_cmd.add_argument("--out", type=Path, default=None)
    generate_cmd.add_argument("--width", type=int, default=480)
    generate_cmd.add_argument("--height", type=int, default=704)
    generate_cmd.add_argument("--duration", type=int, default=3)
    generate_cmd.add_argument("--timeout", type=int, default=1800)
    generate_cmd.add_argument("--seed", type=int, default=123456)
    generate_cmd.add_argument("--profile", default="auto")
    generate_cmd.add_argument("--weapon-intent", default="general")
    generate_cmd.add_argument("--production-stage", default="production")
    generate_cmd.add_argument("--allow-experimental", action="store_true")
    generate_cmd.add_argument("--subject-basis", default=None)
    generate_cmd.add_argument("--turbo", action="store_true")
    generate_cmd.add_argument("--receipt", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "probe":
        report = probe(args.base_url)
    else:
        print(json.dumps({"ok": False, "error": WAN22_I2V_RETIRED}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
