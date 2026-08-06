from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from i2v_provider import (  # noqa: E402
    I2VProviderError,
    all_providers,
    for_endpoint,
    generate_with_fallback,
    get,
    provider_priority,
    provider_switch_receipt_is_valid,
)


def test_registry_contains_only_cloud_action_lanes() -> None:
    import config_loader as cl

    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "ltx23_primary"}, clear=False):
        cl._CONFIG = None
        cl._CONFIG_ENV_FINGERPRINT = None
        assert provider_priority() == ("frw-ltx23", "frw-api-i2v", "grok")
    assert "comfy-wan22" not in all_providers()
    assert "frw-wan" not in all_providers()
    assert for_endpoint("local_wan22_i2v") is None
    assert for_endpoint("frw_img2video").name == "frw-api-i2v"


def test_h3_primary_provider_priority_is_local_then_grok() -> None:
    import config_loader as cl

    with mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "h3_primary"}, clear=False):
        cl._CONFIG = None
        cl._CONFIG_ENV_FINGERPRINT = None
        assert provider_priority() == ("comfy-h3", "grok")


def test_frw_api_canary_requires_bound_approved_media() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        output = root / "out" / "canary.mp4"
        output.parent.mkdir()
        output.write_bytes(b"FRW I2V")
        receipt = root / "receipts" / "frw-api-i2v-canary.json"
        receipt.parent.mkdir()
        receipt.write_text(
            json.dumps(
                {
                    "ok": True,
                    "provider_model": "classic-img2video",
                    "output": str(output),
                    "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                    "full_decode_ok": True,
                    "human_review": "approved",
                }
            ),
            encoding="utf-8",
        )
        with mock.patch(
            "media_qa.analyze_media",
            return_value={"ok": True, "decode_ok": True, "width": 704, "height": 1280},
        ):
            assert get("frw-api-i2v").probe(root=root).available
        output.unlink()
        assert not get("frw-api-i2v").probe(root=root).available


def test_technical_failures_follow_cloud_order_and_are_signed() -> None:
    class Provider:
        def __init__(self, name: str, error: str | None = None) -> None:
            self.name, self.error = name, error

        def probe(self, **_kwargs):
            return SimpleNamespace(available=True, reason="ready")

        def generate(self, **_kwargs):
            if self.error:
                raise I2VProviderError(self.error)
            return {"ok": True, "provider": self.name}

    providers = {
        "frw-ltx23": Provider("frw-ltx23", "HTTP 503"),
        "frw-api-i2v": Provider("frw-api-i2v", "HTTP 429"),
        "grok": Provider("grok"),
    }
    import config_loader as cl

    with (
        tempfile.TemporaryDirectory() as raw,
        mock.patch.dict(
            os.environ,
            {
                "AIFILM_PROVIDER_SWITCH_RECEIPT_KEY": "k" * 32,
                "AIFILM_I2V_PROFILE": "ltx23_primary",
            },
            clear=False,
        ),
        mock.patch("i2v_provider.get", side_effect=lambda name: providers[name]),
    ):
        cl._CONFIG = None
        cl._CONFIG_ENV_FINGERPRINT = None
        result = generate_with_fallback(
            root=Path(raw),
            shot_id="shot01",
            keyframe=Path(raw) / "frame.png",
            prompt="action",
            plan_sha256="a" * 64,
        )
        assert all(provider_switch_receipt_is_valid(row) for row in result["provider_switches"])
    assert result["route"] == "grok_fallback"
    assert [row["provider"] for row in result["routing_attempts"]] == [
        "frw-ltx23",
        "frw-api-i2v",
        "grok",
    ]
    assert [
        (row["primary_provider"], row["fallback_provider"]) for row in result["provider_switches"]
    ] == [("frw-ltx23", "frw-api-i2v"), ("frw-api-i2v", "grok")]


def test_quality_failure_does_not_switch() -> None:
    class Provider:
        name = "frw-ltx23"

        def probe(self, **_kwargs):
            return SimpleNamespace(available=True, reason="ready")

        def generate(self, **_kwargs):
            raise I2VProviderError("quality rejection")

    with mock.patch("i2v_provider.get", return_value=Provider()):
        with pytest.raises(I2VProviderError):
            generate_with_fallback(
                root=None,
                shot_id="shot01",
                keyframe=Path("/tmp/frame.png"),
                prompt="action",
                plan_sha256="a" * 64,
            )


def test_grok_fallback_is_pinned_to_video_15() -> None:
    command = get("grok").build_command(
        keyframe=Path("/tmp/frame.png"), prompt="action", out=Path("/tmp/out.mp4")
    )
    assert command[command.index("--model") + 1] == "grok-imagine-video-1.5"


def test_grok_canary_requires_video_15_and_decoded_media() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        output = root / "out" / "canary.mp4"
        output.parent.mkdir()
        output.write_bytes(b"GROK I2V")
        receipt = root / "receipts" / "grok-i2v-canary.json"
        receipt.parent.mkdir()
        receipt.write_text(
            json.dumps(
                {
                    "ok": True,
                    "provider_model": "grok-imagine-video-1.5",
                    "output": str(output),
                    "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                }
            ),
            encoding="utf-8",
        )
        with mock.patch(
            "media_qa.analyze_media",
            return_value={"ok": True, "decode_ok": True, "width": 704, "height": 1280},
        ):
            assert get("grok").probe(root=root).available
        data = json.loads(receipt.read_text(encoding="utf-8"))
        data["provider_model"] = "grok-imagine-video"
        receipt.write_text(json.dumps(data), encoding="utf-8")
        assert not get("grok").probe(root=root).available

def test_h3_primary_technical_failure_falls_to_grok_with_receipt() -> None:
    """Under free-local h3_primary, Grok Video 1.5 is technical 兜底 only."""
    import config_loader as cl

    class Provider:
        def __init__(self, name: str, error: str | None = None) -> None:
            self.name, self.error = name, error

        def probe(self, **_kwargs):
            return SimpleNamespace(available=True, reason="ready")

        def generate(self, **_kwargs):
            if self.error:
                raise I2VProviderError(self.error)
            return {"ok": True, "provider": self.name}

    providers = {
        "comfy-h3": Provider("comfy-h3", "HTTP 503"),
        "grok": Provider("grok"),
    }
    with (
        tempfile.TemporaryDirectory() as raw,
        mock.patch.dict(
            os.environ,
            {
                "AIFILM_PROVIDER_SWITCH_RECEIPT_KEY": "k" * 32,
                "AIFILM_I2V_PROFILE": "h3_primary",
            },
            clear=False,
        ),
        mock.patch("i2v_provider.get", side_effect=lambda name: providers[name]),
    ):
        cl._CONFIG = None
        cl._CONFIG_ENV_FINGERPRINT = None
        result = generate_with_fallback(
            root=Path(raw),
            shot_id="shot01",
            keyframe=Path(raw) / "frame.png",
            prompt="action",
            plan_sha256="a" * 64,
        )
        assert all(provider_switch_receipt_is_valid(row) for row in result["provider_switches"])
    assert result["route"] == "grok_fallback"
    assert [row["provider"] for row in result["routing_attempts"]] == ["comfy-h3", "grok"]
    assert result["provider_switches"][0]["primary_provider"] == "comfy-h3"
    assert result["provider_switches"][0]["fallback_provider"] == "grok"
    assert result["provider_switches"][0]["reason_class"] == "technical_failure"


def test_h3_primary_quality_failure_does_not_switch_to_grok() -> None:
    import config_loader as cl

    class Provider:
        name = "comfy-h3"

        def probe(self, **_kwargs):
            return SimpleNamespace(available=True, reason="ready")

        def generate(self, **_kwargs):
            raise I2VProviderError("quality rejection")

    with (
        mock.patch.dict(os.environ, {"AIFILM_I2V_PROFILE": "h3_primary"}, clear=False),
        mock.patch("i2v_provider.get", return_value=Provider()),
    ):
        cl._CONFIG = None
        cl._CONFIG_ENV_FINGERPRINT = None
        with pytest.raises(I2VProviderError, match="quality rejection"):
            generate_with_fallback(
                root=None,
                shot_id="shot01",
                keyframe=Path("/tmp/frame.png"),
                prompt="action",
                plan_sha256="a" * 64,
            )

