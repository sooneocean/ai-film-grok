#!/usr/bin/env python3
"""Read-only readiness probe for the SeedVR2 ComfyUI research weapon."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from typing import Any

from comfy_armory import default_base_url
from comfy_video import _json_request, normalize_base_url

REQUIRED_CLASS_TYPES = (
    "SeedVR2LoadDiTModel",
    "SeedVR2LoadVAEModel",
    "SeedVR2TorchCompileSettings",
    "SeedVR2VideoUpscaler",
)


def _model_candidates(object_info: Mapping[str, Any]) -> list[str]:
    loader = object_info.get("SeedVR2LoadDiTModel")
    if not isinstance(loader, Mapping):
        return []
    inputs = loader.get("input")
    if not isinstance(inputs, Mapping):
        return []
    required = inputs.get("required")
    if not isinstance(required, Mapping):
        return []
    model_contract = required.get("model")
    if (
        not isinstance(model_contract, Sequence)
        or isinstance(model_contract, (str, bytes))
        or len(model_contract) < 2
    ):
        return []
    descriptor = model_contract[1]
    choices = descriptor.get("options") if isinstance(descriptor, Mapping) else model_contract[0]
    if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes)):
        return []
    return sorted({item for item in choices if isinstance(item, str) and item.strip()})


def probe_seedvr2(base_url: str) -> dict[str, Any]:
    """Prove only the custom-node contract; never load or download a model."""
    normalized_url = normalize_base_url(base_url)
    object_info = _json_request(normalized_url, "/object_info")
    if not isinstance(object_info, Mapping):
        raise RuntimeError("SeedVR2 probe received invalid ComfyUI object_info")

    missing = sorted(
        class_type for class_type in REQUIRED_CLASS_TYPES if class_type not in object_info
    )
    candidates = _model_candidates(object_info)
    nodes_ready = not missing
    model_contract_ready = bool(candidates)
    upscaler = object_info.get("SeedVR2VideoUpscaler")
    module = str(upscaler.get("python_module") or "") if isinstance(upscaler, Mapping) else ""

    return {
        "schema_version": 1,
        "kind": "seedvr2-readiness-probe",
        "ok": True,
        "base_url": normalized_url,
        "required_class_types": list(REQUIRED_CLASS_TYPES),
        "missing_class_types": missing,
        "custom_nodes_ready": nodes_ready,
        "model_contract_ready": model_contract_ready,
        "model_candidates": candidates,
        "python_module": module or None,
        "weights_state": "unverified",
        "execution_ready": False,
        "auto_download_blocked": True,
        "readiness": (
            "custom_nodes_ready_weights_unverified"
            if nodes_ready and model_contract_ready
            else "custom_node_contract_incomplete"
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Probe SeedVR2 custom-node readiness without loading or downloading weights."
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="ComfyUI base URL; defaults to the verified armory node.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = probe_seedvr2(args.base_url or default_base_url())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["custom_nodes_ready"] and report["model_contract_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
