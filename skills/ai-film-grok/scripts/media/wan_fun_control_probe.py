#!/usr/bin/env python3
"""非生产 · research-only readiness probe for Wan 2.2 Fun Control (not film spine)."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from typing import Any

from comfy_armory import default_base_url
from comfy_video import _json_request, normalize_base_url

REQUIRED_CLASS_TYPES = (
    "Wan22FunControlToVideo",
    "WanFunControlToVideo",
    "CLIPVisionLoader",
)
REQUIRED_MODELS = {
    "diffusion_models": [
        "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
        "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
    ],
    "clip_vision": "wan2.2_clip_vision.safetensors",
}


def _model_names(value: Any) -> set[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return set()
    return {item.strip() for item in value if isinstance(item, str) and item.strip()}


def _missing_models(discovered_models: Mapping[str, set[str]]) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for family, expected in REQUIRED_MODELS.items():
        names = (expected,) if isinstance(expected, str) else expected
        absent = [name for name in names if name not in discovered_models[family]]
        if absent:
            missing[family] = absent
    return missing


def probe_wan_fun_control(base_url: str) -> dict[str, Any]:
    """Prove named dependencies only; never submit, load, or download a model."""
    normalized_url = normalize_base_url(base_url)
    object_info = _json_request(normalized_url, "/object_info")
    if not isinstance(object_info, Mapping):
        raise RuntimeError("Wan Fun Control probe received invalid ComfyUI object_info")

    discovered_models = {
        family: _model_names(_json_request(normalized_url, f"/models/{family}"))
        for family in REQUIRED_MODELS
    }
    missing_class_types = sorted(
        class_type for class_type in REQUIRED_CLASS_TYPES if class_type not in object_info
    )
    missing_weights = _missing_models(discovered_models)
    class_types_ready = not missing_class_types
    named_weights_present = not missing_weights

    return {
        "schema_version": 1,
        "kind": "wan22-fun-control-readiness-probe",
        "ok": True,
        "base_url": normalized_url,
        "required_class_types": list(REQUIRED_CLASS_TYPES),
        "missing_class_types": missing_class_types,
        "required_models": REQUIRED_MODELS,
        "missing_weights": missing_weights,
        "class_types_ready": class_types_ready,
        "named_weights_present": named_weights_present,
        "weights_state": (
            "named_present_fingerprint_unverified"
            if named_weights_present
            else "missing_or_unverified"
        ),
        "execution_ready": False,
        "auto_download_blocked": True,
        "auto_submission_blocked": True,
        "readiness": (
            "named_dependencies_present_fingerprint_unverified"
            if class_types_ready and named_weights_present
            else "dependency_contract_incomplete"
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe Wan 2.2 Fun Control without loading, downloading, or submitting."
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="ComfyUI base URL; defaults to the verified armory node.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = probe_wan_fun_control(args.base_url or default_base_url())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["class_types_ready"] and report["named_weights_present"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
