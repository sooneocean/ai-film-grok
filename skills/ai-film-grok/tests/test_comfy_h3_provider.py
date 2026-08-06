from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from i2v_provider import LocalComfyH3Provider, for_endpoint, get  # noqa: E402
from media_qa import ALLOWED_VIDEO_ENDPOINTS  # noqa: E402


def test_comfy_h3_is_registered() -> None:
    provider = get("comfy-h3")
    assert isinstance(provider, LocalComfyH3Provider)
    assert for_endpoint("local_minimax_h3_i2v") is provider
    assert for_endpoint("local_minimax_h3_t2v") is provider
    assert for_endpoint("local_minimax_h3_r2v") is provider


def test_comfy_h3_endpoints_allowed_for_register() -> None:
    assert "local_minimax_h3_t2v" in ALLOWED_VIDEO_ENDPOINTS
    assert "local_minimax_h3_i2v" in ALLOWED_VIDEO_ENDPOINTS
    assert "local_minimax_h3_r2v" in ALLOWED_VIDEO_ENDPOINTS


def test_comfy_h3_weapon_resolution() -> None:
    assert LocalComfyH3Provider._resolve_weapon("t2v") == (
        "text-to-video",
        "minimax-h3-t2v-pilot",
    )
    assert LocalComfyH3Provider._resolve_weapon("i2v") == (
        "image-to-video",
        "minimax-h3-i2v-pilot",
    )
    assert LocalComfyH3Provider._resolve_weapon("r2v") == (
        "reference-to-video",
        "minimax-h3-r2v-pilot",
    )
