from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from comfy_armory import load_armory  # noqa: E402
from media.wan_fun_control_probe import (  # noqa: E402
    REQUIRED_CLASS_TYPES,
    REQUIRED_MODELS,
    probe_wan_fun_control,
)


def _object_info(*, complete: bool = True) -> dict[str, object]:
    classes = {class_type: {} for class_type in REQUIRED_CLASS_TYPES}
    if not complete:
        classes.pop("Wan22FunControlToVideo")
    return classes


@patch("media.wan_fun_control_probe._json_request")
def test_probe_proves_named_dependencies_without_claiming_execution_ready(
    request: MagicMock,
) -> None:
    request.side_effect = lambda _url, route: {
        "/object_info": _object_info(),
        "/models/diffusion_models": list(REQUIRED_MODELS["diffusion_models"]),
        "/models/clip_vision": [REQUIRED_MODELS["clip_vision"]],
    }[route]

    report = probe_wan_fun_control("http://127.0.0.1:18188")

    assert [call.args[1] for call in request.call_args_list] == [
        "/object_info",
        "/models/diffusion_models",
        "/models/clip_vision",
    ]
    assert report["class_types_ready"] is True
    assert report["named_weights_present"] is True
    assert report["weights_state"] == "named_present_fingerprint_unverified"
    assert report["execution_ready"] is False
    assert report["auto_download_blocked"] is True
    assert report["auto_submission_blocked"] is True


@patch("media.wan_fun_control_probe._json_request")
def test_probe_fails_closed_when_clip_vision_dependency_is_missing(
    request: MagicMock,
) -> None:
    request.side_effect = lambda _url, route: {
        "/object_info": _object_info(),
        "/models/diffusion_models": list(REQUIRED_MODELS["diffusion_models"]),
        "/models/clip_vision": [],
    }[route]

    report = probe_wan_fun_control("http://127.0.0.1:18188")

    assert report["named_weights_present"] is False
    assert report["missing_weights"] == {"clip_vision": [REQUIRED_MODELS["clip_vision"]]}
    assert report["execution_ready"] is False


@patch("media.wan_fun_control_probe._json_request")
def test_probe_fails_closed_when_fun_control_node_is_missing(
    request: MagicMock,
) -> None:
    request.side_effect = lambda _url, route: {
        "/object_info": _object_info(complete=False),
        "/models/diffusion_models": list(REQUIRED_MODELS["diffusion_models"]),
        "/models/clip_vision": [REQUIRED_MODELS["clip_vision"]],
    }[route]

    report = probe_wan_fun_control("http://127.0.0.1:18188")

    assert report["class_types_ready"] is False
    assert report["missing_class_types"] == ["Wan22FunControlToVideo"]
    assert report["execution_ready"] is False


def test_registry_keeps_wan_fun_control_research_only_and_non_promotable() -> None:
    weapon = next(
        item
        for item in load_armory()["research_weapons"]
        if item["id"] == "wan22-fun-control-research"
    )

    assert weapon["allowed_stages"] == ["research"]
    assert weapon["execution_ready"] is False
    assert set(weapon["required_class_types"]) == set(REQUIRED_CLASS_TYPES)
    assert weapon["required_models"] == REQUIRED_MODELS
    assert {
        "no_auto_download",
        "no_auto_execute",
        "no_auto_promotion",
        "not_final",
        "control_video_rights_required",
    }.issubset(weapon["restrictions"])
