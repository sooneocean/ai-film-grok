"""Comfy tunnel ensure: Tailscale CGNAT allowed; 8189 refused."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from comfy_recovery import (  # noqa: E402
    ComfyRecoveryConfig,
    ComfyRecoveryError,
    validate_recovery_config,
)


def _cfg(target: str, *, remote_port: int = 8188) -> ComfyRecoveryConfig:
    return ComfyRecoveryConfig(
        target=target,
        identity_file=Path.home() / ".ssh" / "aifilm_5090_ed25519",
        local_port=18188,
        remote_port=remote_port,
        remote_root=r"C:\ComfyUI_windows_portable",
        known_hosts_file=Path.home() / ".ssh" / "known_hosts",
        hostkey_alias=target.rsplit("@", 1)[-1],
    )


def test_tailscale_cgnat_target_allowed() -> None:
    if not (Path.home() / ".ssh" / "aifilm_5090_ed25519").is_file():
        pytest.skip("no local 5090 key")
    if not (Path.home() / ".ssh" / "known_hosts").is_file():
        pytest.skip("no known_hosts")
    checked = validate_recovery_config(_cfg("user@100.66.2.28"))
    assert checked.target.endswith("100.66.2.28")


def test_public_ip_rejected() -> None:
    with pytest.raises(ComfyRecoveryError, match="RFC1918|Tailscale"):
        validate_recovery_config(_cfg("user@8.8.8.8"))
