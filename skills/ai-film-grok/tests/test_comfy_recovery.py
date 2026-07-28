from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from comfy_recovery import (  # noqa: E402
    ComfyRecoveryConfig,
    ComfyRecoveryError,
    config_from_env,
    recover_comfy,
    validate_recovery_config,
)


def _config(tmp_path: Path) -> ComfyRecoveryConfig:
    key = tmp_path / ".ssh" / "aifilm_5090_ed25519"
    key.parent.mkdir()
    key.write_text("test-key-placeholder", encoding="utf-8")
    key.chmod(0o600)
    return ComfyRecoveryConfig(
        target="user@192.168.88.52",
        identity_file=key,
        local_port=18188,
        remote_port=8188,
        remote_root=r"C:\ComfyUI_windows_portable",
    )


def test_recovery_config_rejects_public_or_malformed_target(tmp_path: Path) -> None:
    config = _config(tmp_path)
    for target in (
        "user@example.com",
        "user@8.8.8.8",
        "user@127.0.0.1",
        "user@169.254.1.1",
        "user@192.0.2.1",
        "user@198.18.0.1",
        "root;touch@192.168.88.52",
    ):
        with pytest.raises(ComfyRecoveryError):
            validate_recovery_config(
                ComfyRecoveryConfig(
                    target=target,
                    identity_file=config.identity_file,
                    local_port=config.local_port,
                    remote_port=config.remote_port,
                    remote_root=config.remote_root,
                )
            )


def test_recovery_config_rejects_group_readable_identity(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.identity_file.chmod(0o640)
    with pytest.raises(ComfyRecoveryError, match="owner-only"):
        validate_recovery_config(config)


def test_recovery_config_rejects_symlink_identity(tmp_path: Path) -> None:
    config = _config(tmp_path)
    link = tmp_path / "linked-key"
    link.symlink_to(config.identity_file)
    with pytest.raises(ComfyRecoveryError, match="unsafe"):
        validate_recovery_config(
            ComfyRecoveryConfig(
                target=config.target,
                identity_file=link,
                local_port=config.local_port,
                remote_port=config.remote_port,
                remote_root=config.remote_root,
            )
        )


def test_recovery_config_rejects_symlinked_identity_parent(tmp_path: Path) -> None:
    config = _config(tmp_path)
    linked_parent = tmp_path / "linked-ssh"
    linked_parent.symlink_to(config.identity_file.parent, target_is_directory=True)
    with pytest.raises(ComfyRecoveryError, match="unsafe"):
        validate_recovery_config(
            ComfyRecoveryConfig(
                target=config.target,
                identity_file=linked_parent / config.identity_file.name,
                local_port=config.local_port,
                remote_port=config.remote_port,
                remote_root=config.remote_root,
            )
        )


def test_recovery_config_rejects_remote_path_traversal(tmp_path: Path) -> None:
    config = _config(tmp_path)
    for remote_root in (
        r"C:\safe\..\ComfyUI_windows_portable",
        r"\\server\share\ComfyUI_windows_portable",
        r"\\?\C:\ComfyUI_windows_portable",
        r"C:\evil -Command x\ComfyUI_windows_portable",
    ):
        with pytest.raises(ComfyRecoveryError, match="root is unsafe"):
            validate_recovery_config(
                ComfyRecoveryConfig(
                    target=config.target,
                    identity_file=config.identity_file,
                    local_port=config.local_port,
                    remote_port=config.remote_port,
                    remote_root=remote_root,
                )
            )


def test_recovery_env_rejects_non_integer_ports() -> None:
    with pytest.raises(ComfyRecoveryError, match="ports must be integers"):
        config_from_env({"AIFILM_COMFY_TUNNEL_PORT": "not-a-port"})


def test_empty_explicit_environment_uses_documented_defaults() -> None:
    config = config_from_env({})
    assert config.target == "user@192.168.88.52"
    assert config.local_port == 18188
    assert config.remote_port == 8188


def test_healthy_local_node_is_a_zero_mutation_noop(tmp_path: Path) -> None:
    local_probe = MagicMock(return_value=True)
    remote_probe = MagicMock()
    run_remote = MagicMock()
    start_tunnel = MagicMock()

    report = recover_comfy(
        _config(tmp_path),
        confirm=True,
        local_probe=local_probe,
        remote_probe=remote_probe,
        run_remote=run_remote,
        start_tunnel=start_tunnel,
    )

    assert report["ok"] is True
    assert report["action"] == "none"
    remote_probe.assert_not_called()
    run_remote.assert_not_called()
    start_tunnel.assert_not_called()


def test_remote_healthy_repairs_only_tunnel(tmp_path: Path) -> None:
    local_probe = MagicMock(side_effect=[False, True])
    remote_probe = MagicMock(return_value=True)
    run_remote = MagicMock()
    start_tunnel = MagicMock()

    report = recover_comfy(
        _config(tmp_path),
        confirm=True,
        local_probe=local_probe,
        remote_probe=remote_probe,
        run_remote=run_remote,
        start_tunnel=start_tunnel,
    )

    assert report["ok"] is True
    assert report["action"] == "tunnel_repaired"
    run_remote.assert_not_called()
    start_tunnel.assert_called_once()


def test_transient_remote_probe_failure_does_not_restart_service(tmp_path: Path) -> None:
    local_probe = MagicMock(side_effect=[False, True])
    remote_probe = MagicMock(side_effect=[False, True])
    run_remote = MagicMock()
    start_tunnel = MagicMock()

    report = recover_comfy(
        _config(tmp_path),
        confirm=True,
        local_probe=local_probe,
        remote_probe=remote_probe,
        run_remote=run_remote,
        start_tunnel=start_tunnel,
        sleeper=MagicMock(),
    )

    assert report["action"] == "tunnel_repaired"
    run_remote.assert_not_called()
    assert remote_probe.call_count == 2


def test_remote_failure_restarts_only_comfy_then_repairs_tunnel(tmp_path: Path) -> None:
    local_probe = MagicMock(side_effect=[False, True])
    remote_probe = MagicMock(side_effect=[False, False, False, True])
    run_remote = MagicMock()
    start_tunnel = MagicMock()

    report = recover_comfy(
        _config(tmp_path),
        confirm=True,
        local_probe=local_probe,
        remote_probe=remote_probe,
        run_remote=run_remote,
        start_tunnel=start_tunnel,
        sleeper=MagicMock(),
    )

    assert report["ok"] is True
    assert report["action"] == "service_restarted_and_tunnel_repaired"
    assert [call.args[1] for call in run_remote.call_args_list] == ["stop", "start"]
    start_tunnel.assert_called_once()
    serialized = str(report)
    assert "192.168.88.52" not in serialized
    assert "aifilm_5090_ed25519" not in serialized


def test_recovery_requires_explicit_confirmation(tmp_path: Path) -> None:
    with pytest.raises(ComfyRecoveryError, match="confirmation"):
        recover_comfy(
            _config(tmp_path),
            confirm=False,
            local_probe=MagicMock(return_value=False),
            remote_probe=MagicMock(),
            run_remote=MagicMock(),
            start_tunnel=MagicMock(),
        )
