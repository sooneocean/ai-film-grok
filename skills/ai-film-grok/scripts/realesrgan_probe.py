#!/usr/bin/env python3
"""Read-only readiness probe for Real-ESRGAN formal-upscale research weapon.

Never downloads weights, never submits Comfy prompts, never promotes media.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

# Optional Comfy class names used by common ESRGAN custom nodes / core loaders.
COMFY_UPSCALE_HINT_CLASSES = (
    "UpscaleModelLoader",
    "ImageUpscaleWithModel",
    "VideoUpscaleWithModel",
)

PREFERRED_WEIGHT_NAMES = (
    "realesr-animevideov3.pth",
    "RealESRGAN_x4plus_anime_6B.pth",
    "RealESRGAN_x4plus.pth",
    "realesrgan-x4plus.pth",
)


def _which_backends() -> dict[str, Any]:
    found: dict[str, Any] = {
        "realesrgan_ncnn_vulkan": None,
        "inference_realesrgan_video_py": None,
        "python_realesrgan_module": False,
    }
    for name in (
        "realesrgan-ncnn-vulkan",
        "realesrgan-ncnn-vulkan.exe",
    ):
        path = shutil.which(name)
        if path:
            found["realesrgan_ncnn_vulkan"] = path
            break
    # Common local clone path (user opt-in; never required).
    env_root = os.environ.get("AIFILM_REALESRGAN_ROOT", "").strip()
    candidates: list[Path] = []
    if env_root:
        candidates.append(Path(env_root).expanduser())
    candidates.extend(
        [
            Path.home() / "Real-ESRGAN",
            Path.home() / "src" / "Real-ESRGAN",
            Path.home() / "Developer" / "Real-ESRGAN",
        ]
    )
    for root in candidates:
        script = root / "inference_realesrgan_video.py"
        if script.is_file():
            found["inference_realesrgan_video_py"] = str(script.resolve())
            break
    try:
        import importlib.util

        found["python_realesrgan_module"] = importlib.util.find_spec("realesrgan") is not None
    except Exception:  # noqa: BLE001
        found["python_realesrgan_module"] = False
    return found


def _scan_weight_dirs(extra: Sequence[str] | None = None) -> dict[str, Any]:
    dirs: list[Path] = []
    env_dir = os.environ.get("AIFILM_REALESRGAN_WEIGHTS", "").strip()
    if env_dir:
        dirs.append(Path(env_dir).expanduser())
    if extra:
        dirs.extend(Path(p).expanduser() for p in extra)
    # Conventional Comfy layout (read-only existence check; no download).
    comfy_models = os.environ.get("AIFILM_COMFY_MODELS", "").strip()
    if comfy_models:
        base = Path(comfy_models).expanduser()
        dirs.append(base / "upscale_models")
        dirs.append(base / "esrgan")
    home = Path.home()
    dirs.extend(
        [
            home / "Real-ESRGAN" / "weights",
            home / ".cache" / "realesrgan",
        ]
    )
    existing_dirs = [d for d in dirs if d.is_dir()]
    hits: dict[str, str] = {}
    for d in existing_dirs:
        for name in PREFERRED_WEIGHT_NAMES:
            p = d / name
            if p.is_file() and name not in hits:
                hits[name] = str(p.resolve())
            # also allow nested
            if name not in hits:
                nested = list(d.rglob(name))
                if nested:
                    hits[name] = str(nested[0].resolve())
    return {
        "weight_dirs_checked": [str(d) for d in existing_dirs],
        "weights_found": hits,
        "preferred_present": sorted(hits.keys()),
    }


def _probe_comfy(base_url: str | None) -> dict[str, Any]:
    if not base_url:
        return {
            "skipped": True,
            "reason": "no_base_url",
        }
    try:
        from comfy_video import _json_request, normalize_base_url
    except Exception as exc:  # noqa: BLE001
        return {"skipped": True, "reason": f"import_failed:{exc}"}
    try:
        normalized = normalize_base_url(base_url)
        object_info = _json_request(normalized, "/object_info")
    except Exception as exc:  # noqa: BLE001
        return {
            "skipped": False,
            "ok": False,
            "error": str(exc)[:300],
            "base_url": base_url,
        }
    if not isinstance(object_info, Mapping):
        return {"ok": False, "error": "invalid_object_info", "base_url": normalized}
    present = [c for c in COMFY_UPSCALE_HINT_CLASSES if c in object_info]
    return {
        "skipped": False,
        "ok": True,
        "base_url": normalized,
        "hint_classes_present": present,
        "upscale_loader_ready": "UpscaleModelLoader" in object_info,
    }


def probe_realesrgan(
    *,
    base_url: str | None = None,
    weight_dirs: Sequence[str] | None = None,
) -> dict[str, Any]:
    backends = _which_backends()
    # Prefer media.realesrgan_upscale cache defaults (ncnn).
    try:
        from realesrgan_upscale import backend_status, fingerprint_assets

        up = backend_status()
        fps = fingerprint_assets()
        if up.get("ncnn_binary"):
            backends["realesrgan_ncnn_vulkan"] = up.get("ncnn_binary")
        if up.get("ncnn_models"):
            backends["ncnn_models"] = up.get("ncnn_models")
        backends["upscale_module_ready"] = bool(up.get("backend_ready"))
    except Exception as exc:  # noqa: BLE001
        up = {"error": str(exc)[:160]}
        fps = {}
        backends["upscale_module_ready"] = False

    weights = _scan_weight_dirs(weight_dirs)
    # Merge fingerprint keys into preferred_present signal
    if fps:
        weights = dict(weights)
        found = dict(weights.get("weights_found") or {})
        found.update({k: f"sha256:{v[:16]}…" for k, v in fps.items()})
        weights["weights_found"] = found
        weights["preferred_present"] = sorted(
            set(list(weights.get("preferred_present") or []) + list(fps.keys()))
        )
        weights["fingerprints"] = fps

    comfy = _probe_comfy(base_url)
    backend_ready = bool(
        backends.get("realesrgan_ncnn_vulkan")
        or backends.get("inference_realesrgan_video_py")
        or backends.get("python_realesrgan_module")
        or backends.get("upscale_module_ready")
        or (isinstance(comfy, Mapping) and comfy.get("upscale_loader_ready"))
    )
    weights_found = bool(weights.get("preferred_present"))
    # execution_ready when ncnn path works AND fingerprints present (canary gate).
    ncnn_ok = bool(
        (backends.get("realesrgan_ncnn_vulkan") and backends.get("ncnn_models"))
        or backends.get("upscale_module_ready")
    )
    execution_ready = bool(ncnn_ok and weights_found and fps)
    readiness = "spec_ready_weights_unverified"
    if execution_ready:
        readiness = "ncnn_ready_fingerprinted"
    elif backend_ready and weights_found:
        readiness = "backend_and_weights_seen"
    elif backend_ready:
        readiness = "backend_ready_weights_missing"
    elif weights_found:
        readiness = "weights_seen_backend_missing"

    return {
        "schema_version": 1,
        "kind": "realesrgan-readiness-probe",
        "ok": True,
        "weapon_id": "realesrgan-animevideo-research",
        "execution_ready": execution_ready,
        "auto_download_blocked": True,
        "auto_promote_blocked": True,
        "gfpgan_face_enhance_default": False,
        "readiness": readiness,
        "backends": backends,
        "weights": weights,
        "comfy": comfy,
        "upscale_module": up if isinstance(up, dict) else {},
        "backend_ready": backend_ready,
        "weights_seen": weights_found,
        "notes": [
            "default production path remains ffmpeg geometry floor for H3",
            "formal upscale is selects-only; aifilm upscale run never auto-promotes",
            "see references/realesrgan-formal-upscale.md",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe Real-ESRGAN readiness without download/execute/promote."
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Optional ComfyUI base URL for UpscaleModelLoader object_info probe.",
    )
    parser.add_argument(
        "--weight-dir",
        action="append",
        default=None,
        help="Extra directory to scan for .pth weights (repeatable).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = probe_realesrgan(base_url=args.base_url, weight_dirs=args.weight_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    # Exit 0 always for soft probe usability; use fields for gates later.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
