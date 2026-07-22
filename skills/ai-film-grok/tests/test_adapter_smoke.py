"""Smoke tests for all I2V/TTS/BGM adapters.

Verifies each adapter module imports and exposes the expected interface
without making network calls.
"""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ADAPTERS = SCRIPTS / "adapters"


ADAPTER_EXPECTATIONS = {
    "grok_oauth_image": {"class": "GrokOAuthImageProvider", "methods": ["generate", "edit"]},
    "grok_oauth_image_edit": {"class": "GrokOAuthImageEditProvider", "methods": ["edit"]},
    "grok_oauth_video": {"class": "GrokOAuthVideoProvider", "methods": ["image_to_video"]},
    "grok_oauth_tts": {"class": "GrokOAuthTTSProvider", "methods": ["synthesize"]},
    "voicebox_tts": {"class": "VoiceboxTTSProvider", "methods": ["synthesize"]},
    "elevenlabs_tts": {"class": "ElevenLabsTTSProvider", "methods": ["synthesize"]},
    "cosyvoice_tts": {"class": "CosyVoiceTTSProvider", "methods": ["synthesize"]},
    "music_external": {"class": "MusicExternalProvider", "methods": ["resolve_bed"]},
}


@pytest.mark.parametrize("module_name", sorted(ADAPTER_EXPECTATIONS.keys()))
def test_adapter_imports(module_name: str) -> None:
    """Each adapter module must import without error."""
    try:
        importlib.import_module(module_name)
    except ImportError as exc:
        pytest.skip(f"adapter {module_name} has missing optional deps: {exc}")


@pytest.mark.parametrize("module_name", sorted(ADAPTER_EXPECTATIONS.keys()))
def test_adapter_exposes_class(module_name: str) -> None:
    """Each adapter must expose its expected provider class."""
    try:
        mod = importlib.import_module(module_name)
    except ImportError as exc:
        pytest.skip(f"adapter {module_name} has missing optional deps: {exc}")

    expected = ADAPTER_EXPECTATIONS[module_name]
    cls_name = expected["class"]
    assert hasattr(mod, cls_name), f"{module_name} missing class {cls_name}"
    cls = getattr(mod, cls_name)
    assert inspect.isclass(cls), f"{module_name}.{cls_name} is not a class"


@pytest.mark.parametrize("module_name", sorted(ADAPTER_EXPECTATIONS.keys()))
def test_adapter_exposes_methods(module_name: str) -> None:
    """Each adapter class must expose its expected methods."""
    try:
        mod = importlib.import_module(module_name)
    except ImportError as exc:
        pytest.skip(f"adapter {module_name} has missing optional deps: {exc}")

    expected = ADAPTER_EXPECTATIONS[module_name]
    cls = getattr(mod, expected["class"])
    for method_name in expected["methods"]:
        assert hasattr(cls, method_name), f"{cls.__name__} missing method {method_name}"
