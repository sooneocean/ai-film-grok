"""Bounded SSH recovery for the private ComfyUI node."""

from __future__ import annotations

import ipaddress
import os
import re
import stat
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from security_policy import load_allowed_env, minimal_subprocess_env


class ComfyRecoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class ComfyRecoveryConfig:
    target: str
    identity_file: Path
    local_port: int
    remote_port: int
    remote_root: str
    known_hosts_file: Path = Path("~/.ssh/known_hosts")
    hostkey_alias: str = ""


# Windows OpenSSH accepts a down-level logon name (``DOMAIN\\user``).  Keep the
# domain optional and bounded so the target remains one argv element, never SSH
# option syntax or a shell fragment.
_TARGET_RE = re.compile(
    r"(?P<user>(?:[A-Za-z0-9][A-Za-z0-9_.-]{0,31}\\)?[A-Za-z0-9][A-Za-z0-9_.-]{0,31})@"
    r"(?P<host>[0-9.]{7,15})"
)
_CONFIG_ESCAPED_TARGET_RE = re.compile(
    r"(?P<domain>[A-Za-z0-9][A-Za-z0-9_.-]{0,31})\\\\"
    r"(?P<user>[A-Za-z0-9][A-Za-z0-9_.-]{0,31})@(?P<host>[0-9.]{7,15})"
)
_HOSTKEY_ALIAS_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_APPROVED_REMOTE_ROOT = r"C:\ComfyUI_windows_portable"


def _normalize_config_target(value: str) -> str:
    """Decode only the bounded Windows domain escape emitted by config files."""
    match = _CONFIG_ESCAPED_TARGET_RE.fullmatch(value)
    if match is None:
        return value
    return f"{match.group('domain')}\\{match.group('user')}@{match.group('host')}"


def config_from_env(
    environ: Mapping[str, str] | None = None,
) -> ComfyRecoveryConfig:
    if environ is None:
        load_allowed_env(
            Path(__file__).resolve().parents[2] / "config.env",
            allowed_keys={
                "AIFILM_COMFY_SSH_TARGET",
                "AIFILM_COMFY_SSH_KEY",
                "AIFILM_COMFY_TUNNEL_PORT",
                "AIFILM_COMFY_REMOTE_PORT",
                "AIFILM_COMFY_BROKER_PORT",
                "AIFILM_COMFY_REMOTE_ROOT",
                "AIFILM_COMFY_SSH_KNOWN_HOSTS",
                "AIFILM_COMFY_SSH_HOSTKEY_ALIAS",
            },
        )
    source = os.environ if environ is None else environ
    try:
        target = _normalize_config_target(
            source.get("AIFILM_COMFY_SSH_TARGET", "user@192.168.88.52").strip()
        )
        return ComfyRecoveryConfig(
            target=target,
            identity_file=Path(
                source.get(
                    "AIFILM_COMFY_SSH_KEY",
                    "~/.ssh/aifilm_5090_ed25519",
                )
            ).expanduser(),
            local_port=int(source.get("AIFILM_COMFY_TUNNEL_PORT", "18188")),
            remote_port=int(
                source.get(
                    "AIFILM_COMFY_REMOTE_PORT",
                    source.get("AIFILM_COMFY_BROKER_PORT", "8188"),
                )
            ),
            remote_root=source.get(
                "AIFILM_COMFY_REMOTE_ROOT",
                r"C:\ComfyUI_windows_portable",
            ).strip(),
            known_hosts_file=Path(
                source.get(
                    "AIFILM_COMFY_SSH_KNOWN_HOSTS",
                    "~/.ssh/known_hosts",
                )
            ).expanduser(),
            hostkey_alias=source.get(
                "AIFILM_COMFY_SSH_HOSTKEY_ALIAS",
                target.rsplit("@", 1)[-1],
            ).strip(),
        )
    except ValueError as exc:
        raise ComfyRecoveryError("ComfyUI recovery ports must be integers") from exc


def validate_recovery_config(config: ComfyRecoveryConfig) -> ComfyRecoveryConfig:
    match = _TARGET_RE.fullmatch(config.target)
    if match is None:
        raise ComfyRecoveryError("SSH target must be user@private-literal-ip")
    try:
        host = ipaddress.ip_address(match.group("host"))
    except ValueError as exc:
        raise ComfyRecoveryError("SSH target has an invalid IP") from exc
    if host.version != 4 or not any(host in network for network in _RFC1918_NETWORKS):
        raise ComfyRecoveryError("SSH recovery target must be an RFC1918 IPv4 address")
    if not 1024 <= config.local_port <= 65535:
        raise ComfyRecoveryError("local tunnel port is outside the safe range")
    if not 1 <= config.remote_port <= 65535:
        raise ComfyRecoveryError("remote ComfyUI port is invalid")
    if config.remote_root.casefold() != _APPROVED_REMOTE_ROOT.casefold():
        raise ComfyRecoveryError("remote ComfyUI root is unsafe")
    hostkey_alias = config.hostkey_alias or match.group("host")
    if _HOSTKEY_ALIAS_RE.fullmatch(hostkey_alias) is None:
        raise ComfyRecoveryError("SSH HostKeyAlias is unsafe")

    expanded_key = config.identity_file.expanduser()
    absolute_key = expanded_key if expanded_key.is_absolute() else Path.cwd() / expanded_key
    if any(part.is_symlink() for part in (absolute_key, *absolute_key.parents)):
        raise ComfyRecoveryError("SSH identity file is missing or unsafe")
    key = absolute_key.resolve()
    if not key.is_file():
        raise ComfyRecoveryError("SSH identity file is missing or unsafe")
    key_stat = key.stat()
    if hasattr(os, "getuid") and key_stat.st_uid != os.getuid():
        raise ComfyRecoveryError("SSH identity file must be owned by the current user")
    mode = stat.S_IMODE(key_stat.st_mode)
    if mode & 0o077:
        raise ComfyRecoveryError("SSH identity file must be owner-only")

    expanded_known_hosts = config.known_hosts_file.expanduser()
    absolute_known_hosts = (
        expanded_known_hosts
        if expanded_known_hosts.is_absolute()
        else Path.cwd() / expanded_known_hosts
    )
    if any(part.is_symlink() for part in (absolute_known_hosts, *absolute_known_hosts.parents)):
        raise ComfyRecoveryError("SSH known_hosts file is missing or unsafe")
    known_hosts = absolute_known_hosts.resolve()
    if not known_hosts.is_file():
        raise ComfyRecoveryError("SSH known_hosts file is missing or unsafe")
    known_hosts_stat = known_hosts.stat()
    if hasattr(os, "getuid") and known_hosts_stat.st_uid != os.getuid():
        raise ComfyRecoveryError("SSH known_hosts file must be owned by the current user")
    known_hosts_mode = stat.S_IMODE(known_hosts_stat.st_mode)
    if known_hosts_mode & 0o077:
        raise ComfyRecoveryError("SSH known_hosts file must be owner-only")
    return ComfyRecoveryConfig(
        target=config.target,
        identity_file=key,
        local_port=config.local_port,
        remote_port=config.remote_port,
        remote_root=config.remote_root,
        known_hosts_file=known_hosts,
        hostkey_alias=hostkey_alias,
    )


def _local_probe(config: ComfyRecoveryConfig) -> bool:
    url = f"http://127.0.0.1:{config.local_port}/system_stats"
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _ssh_base(config: ComfyRecoveryConfig) -> list[str]:
    return [
        "ssh",
        "-i",
        str(config.identity_file),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={config.known_hosts_file}",
        "-o",
        f"HostKeyAlias={config.hostkey_alias}",
        "-o",
        "ConnectTimeout=10",
        config.target,
    ]


def _remote_probe(config: ComfyRecoveryConfig) -> bool:
    command = [
        *_ssh_base(config),
        "curl.exe",
        "-fsS",
        "--max-time",
        "8",
        f"http://127.0.0.1:{config.remote_port}/system_stats",
        "-o",
        "NUL",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=20,
            env=minimal_subprocess_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _run_remote(config: ComfyRecoveryConfig, action: str) -> None:
    if action not in {"stop", "start"}:
        raise ComfyRecoveryError("unsupported remote recovery action")
    script = f"{config.remote_root}\\{action}_comfyui.ps1"
    command = [
        *_ssh_base(config),
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "RemoteSigned",
        "-File",
        script,
        "-Port",
        str(config.remote_port),
    ]
    if action == "start":
        command.extend(["-Host", "127.0.0.1"])
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=90,
            env=minimal_subprocess_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ComfyRecoveryError(f"remote ComfyUI {action} command failed") from exc
    if result.returncode != 0:
        raise ComfyRecoveryError(f"remote ComfyUI {action} command exited {result.returncode}")


def _start_tunnel(config: ComfyRecoveryConfig) -> None:
    forward = f"127.0.0.1:{config.local_port}:127.0.0.1:{config.remote_port}"
    command = [
        "ssh",
        "-i",
        str(config.identity_file),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={config.known_hosts_file}",
        "-o",
        f"HostKeyAlias={config.hostkey_alias}",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=30",
        "-fN",
        "-L",
        forward,
        config.target,
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=20,
            env=minimal_subprocess_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ComfyRecoveryError("SSH tunnel repair failed") from exc
    if result.returncode != 0:
        raise ComfyRecoveryError(
            "SSH tunnel repair failed; inspect the local port owner without killing it"
        )


def recover_comfy(
    config: ComfyRecoveryConfig,
    *,
    confirm: bool,
    local_probe: Callable[[ComfyRecoveryConfig], bool] = _local_probe,
    remote_probe: Callable[[ComfyRecoveryConfig], bool] = _remote_probe,
    run_remote: Callable[[ComfyRecoveryConfig, str], None] = _run_remote,
    start_tunnel: Callable[[ComfyRecoveryConfig], None] = _start_tunnel,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if not confirm:
        raise ComfyRecoveryError("ComfyUI recovery requires explicit confirmation")
    checked = validate_recovery_config(config)
    if local_probe(checked):
        return {
            "schema_version": 1,
            "kind": "comfy-recovery",
            "ok": True,
            "action": "none",
            "local_healthy": True,
            "remote_service_restarted": False,
        }

    class _RemoteNotReady(RuntimeError):
        """Internal: remote probe not healthy yet — util.retry only."""

    def _probe_remote_once() -> bool:
        if remote_probe(checked):
            return True
        raise _RemoteNotReady("remote ComfyUI not healthy")

    from util.retry import retry_call

    try:
        retry_call(
            _probe_remote_once,
            attempts=3,
            delay_sec=1.0,
            backoff=1.0,
            retry_on=(_RemoteNotReady,),
            sleep=sleeper,
        )
        remote_healthy = True
    except _RemoteNotReady:
        remote_healthy = False

    service_restarted = False
    if not remote_healthy:
        run_remote(checked, "stop")
        run_remote(checked, "start")
        service_restarted = True
        for _ in range(15):
            if remote_probe(checked):
                break
            sleeper(2)
        else:
            raise ComfyRecoveryError("remote ComfyUI did not recover before timeout")

    start_tunnel(checked)
    if not local_probe(checked):
        raise ComfyRecoveryError("ComfyUI remained unreachable after tunnel repair")
    return {
        "schema_version": 1,
        "kind": "comfy-recovery",
        "ok": True,
        "action": (
            "service_restarted_and_tunnel_repaired" if service_restarted else "tunnel_repaired"
        ),
        "local_healthy": True,
        "remote_service_restarted": service_restarted,
    }


def recover_comfy_from_env(*, confirm: bool) -> dict[str, Any]:
    return recover_comfy(config_from_env(), confirm=confirm)
