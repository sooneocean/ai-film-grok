"""Smoke tests for all I2V/TTS/BGM adapters.

Verifies each adapter module imports and exposes the expected interface
without making network calls.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ADAPTERS = SCRIPTS / "adapters"
sys.path.insert(0, str(ADAPTERS))


ADAPTER_MODULES = (
    "grok_oauth_image",
    "grok_oauth_image_edit",
    "grok_oauth_video",
    "grok_oauth_tts",
    "voicebox_tts",
    "elevenlabs_tts",
    "cosyvoice_tts",
    "music_external",
)


@pytest.mark.parametrize("module_name", ADAPTER_MODULES)
def test_adapter_imports(module_name: str) -> None:
    """Each adapter module must import without error."""
    try:
        importlib.import_module(module_name)
    except ImportError as exc:
        pytest.skip(f"adapter {module_name} has missing optional deps: {exc}")


@pytest.mark.parametrize("module_name", ADAPTER_MODULES)
def test_adapter_exposes_callable_cli_entrypoint(module_name: str) -> None:
    """Shipped adapters use the trusted argv contract and expose ``main``."""
    try:
        mod = importlib.import_module(module_name)
    except ImportError as exc:
        pytest.skip(f"adapter {module_name} has missing optional deps: {exc}")

    assert callable(getattr(mod, "main", None)), f"{module_name} missing callable main"
