from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from comfy_armory import load_armory  # noqa: E402
from wan_s2v_probe import REQUIRED_CLASS_TYPES, REQUIRED_MODELS, probe_wan_s2v  # noqa: E402


def _object_info(*, complete: bool = True) -> dict[str, object]:
    classes = {class_type: {} for class_type in REQUIRED_CLASS_TYPES}
    if not complete:
        classes.pop("AudioEncoderEncode")
    return classes


@patch("wan_s2v_probe._json_request")
def test_probe_proves_named_inputs_but_never_claims_execution_ready(
    request: MagicMock,
) -> None:
    request.side_effect = lambda _url, route: {
        "/object_info": _object_info(),
        "/models/diffusion_models": [REQUIRED_MODELS["diffusion_models"]],
        "/models/audio_encoders": [REQUIRED_MODELS["audio_encoders"]],
    }[route]

    report = probe_wan_s2v("http://127.0.0.1:18188")

    assert [call.args[1] for call in request.call_args_list] == [
        "/object_info",
        "/models/diffusion_models",
        "/models/audio_encoders",
    ]
    assert report["class_types_ready"] is True
    assert report["named_weights_present"] is True
    assert report["weights_state"] == "named_present_fingerprint_unverified"
    assert report["execution_ready"] is False
    assert report["auto_download_blocked"] is True
    assert report["auto_submission_blocked"] is True


@patch("wan_s2v_probe._json_request")
def test_probe_fails_closed_when_required_audio_encoder_is_missing(
    request: MagicMock,
) -> None:
    request.side_effect = lambda _url, route: {
        "/object_info": _object_info(),
        "/models/diffusion_models": [REQUIRED_MODELS["diffusion_models"]],
        "/models/audio_encoders": [],
    }[route]

    report = probe_wan_s2v("http://127.0.0.1:18188")

    assert report["named_weights_present"] is False
    assert report["missing_weights"] == {"audio_encoders": [REQUIRED_MODELS["audio_encoders"]]}
    assert report["execution_ready"] is False


@patch("wan_s2v_probe._json_request")
def test_probe_fails_closed_when_a_required_node_class_is_missing(
    request: MagicMock,
) -> None:
    request.side_effect = lambda _url, route: {
        "/object_info": _object_info(complete=False),
        "/models/diffusion_models": [REQUIRED_MODELS["diffusion_models"]],
        "/models/audio_encoders": [REQUIRED_MODELS["audio_encoders"]],
    }[route]

    report = probe_wan_s2v("http://127.0.0.1:18188")

    assert report["class_types_ready"] is False
    assert report["missing_class_types"] == ["AudioEncoderEncode"]
    assert report["execution_ready"] is False


def test_registry_keeps_wan_s2v_research_only_and_non_promotable() -> None:
    weapon = next(
        item
        for item in load_armory()["research_weapons"]
        if item["id"] == "wan22-s2v-performance-research"
    )

    assert weapon["allowed_stages"] == ["research"]
    assert set(weapon["required_class_types"]) == set(REQUIRED_CLASS_TYPES)
    assert weapon["required_models"] == REQUIRED_MODELS
    assert {
        "no_auto_download",
        "no_auto_execute",
        "no_auto_promotion",
        "not_final",
        "not_lipsync_substitute",
    }.issubset(weapon["restrictions"])
