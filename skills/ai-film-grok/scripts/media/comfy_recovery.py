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
# Tailscale CGNAT (not public internet) — preferred mesh path for 5090 Windows node
_TAILSCALE_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_APPROVED_REMOTE_ROOT = r"C:\ComfyUI_windows_portable"
# desktop-qfkiqd9 Tailscale IP (2026-08-06); override with AIFILM_COMFY_SSH_TARGET
_DEFAULT_SSH_TARGET = "user@100.66.2.28"


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
            source.get("AIFILM_COMFY_SSH_TARGET", _DEFAULT_SSH_TARGET).strip()
            or _DEFAULT_SSH_TARGET
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
    private_ok = any(host in network for network in _RFC1918_NETWORKS) or host in _TAILSCALE_CGNAT
    if host.version != 4 or not private_ok:
        raise ComfyRecoveryError(
            "SSH recovery target must be RFC1918 or Tailscale CGNAT (100.64/10) IPv4"
        )
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
    # macOS default known_hosts is often 644; forbid only world-writable
    if known_hosts_mode & 0o002:
        raise ComfyRecoveryError("SSH known_hosts file must not be world-writable")
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
    # -F /dev/null: ignore ~/.ssh/config Host rewrites (seen: wrong HostName on Mac)
    return [
        "ssh",
        "-F",
        "/dev/null",
        "-i",
        str(config.identity_file),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"UserKnownHostsFile={config.known_hosts_file}",
        "-o",
        f"HostKeyAlias={config.hostkey_alias or config.target.rsplit('@', 1)[-1]}",
        "-o",
        "ConnectTimeout=15",
        config.target,
    ]


def _kill_stale_local_tunnel(local_port: int) -> list[str]:
    """Best-effort kill only ssh -L forwards on local_port (never kill Comfy itself)."""
    notes: list[str] = []
    try:
        # lsof: ssh holding TCP listen on local_port
        proc = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{local_port}", "-sTCP:LISTEN", "-t"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env=minimal_subprocess_env(),
        )
        pids = [x.strip() for x in (proc.stdout or "").split() if x.strip().isdigit()]
    except (OSError, subprocess.SubprocessError):
        pids = []
    for pid in pids:
        # macOS: ps
        try:
            ps = subprocess.run(
                ["ps", "-p", pid, "-o", "command="],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
                env=minimal_subprocess_env(),
            )
            line = (ps.stdout or "").strip()
        except (OSError, subprocess.SubprocessError):
            line = ""
        if "ssh" not in line.lower() or f"{local_port}:" not in line and f":{local_port}" not in line:
            # require ssh and port marker in argv
            if "ssh" not in line.lower() or str(local_port) not in line:
                notes.append(f"skip_pid_{pid}_not_ssh_forward")
                continue
        try:
            subprocess.run(
                ["kill", pid],
                check=False,
                capture_output=True,
                timeout=3,
                env=minimal_subprocess_env(),
            )
            notes.append(f"killed_stale_ssh_pid_{pid}")
        except (OSError, subprocess.SubprocessError) as exc:
            notes.append(f"kill_failed_{pid}:{exc}")
    return notes


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
    # Explicit bind: local_port → remote loopback:8188 only (never 8189)
    if int(config.remote_port) == 8189:
        raise ComfyRecoveryError("remote port 8189 is lipsync/auth — refuse (use 8188)")
    forward = f"127.0.0.1:{config.local_port}:127.0.0.1:{config.remote_port}"
    command = [
        "ssh",
        "-F",
        "/dev/null",
        "-i",
        str(config.identity_file),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"UserKnownHostsFile={config.known_hosts_file}",
        "-o",
        f"HostKeyAlias={config.hostkey_alias or config.target.rsplit('@', 1)[-1]}",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
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
            timeout=25,
            env=minimal_subprocess_env(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ComfyRecoveryError("SSH tunnel repair failed") from exc
    if result.returncode != 0:
        err = (result.stderr or b"").decode("utf-8", errors="replace")[:200]
        raise ComfyRecoveryError(
            f"SSH tunnel repair failed (rc={result.returncode}): {err or 'no stderr'}"
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
    # Drop dead local listeners before re-bind (zombie -L after remote sleep)
    _kill_stale_local_tunnel(checked.local_port)

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


def ensure_comfy_tunnel(
    *,
    confirm: bool = True,
    restart_remote_if_down: bool = True,
) -> dict[str, Any]:
    """Force-open 18188→8188 tunnel (and start remote Comfy if needed).

    User IRON 2026-08-06: never leave tunnel as manual homework.
    Safe defaults: Tailscale target user@100.66.2.28 · remote 8188 only.
    """
    if not confirm:
        raise ComfyRecoveryError("ensure_comfy_tunnel requires confirm=True")
    config = validate_recovery_config(config_from_env())
    notes: list[str] = []
    if _local_probe(config):
        return {
            "schema_version": 1,
            "kind": "comfy-tunnel-ensure",
            "ok": True,
            "action": "already_healthy",
            "local_port": config.local_port,
            "remote_port": config.remote_port,
            "target": config.target,
            "notes": notes,
        }
    notes.extend(_kill_stale_local_tunnel(config.local_port))
    if not restart_remote_if_down:
        # tunnel only
        _start_tunnel(config)
        ok = _local_probe(config)
        return {
            "schema_version": 1,
            "kind": "comfy-tunnel-ensure",
            "ok": ok,
            "action": "tunnel_only",
            "local_port": config.local_port,
            "remote_port": config.remote_port,
            "target": config.target,
            "notes": notes,
        }
    # Full recovery: remote start if needed + tunnel
    rep = recover_comfy(
        config,
        confirm=True,
        local_probe=_local_probe,
        remote_probe=_remote_probe,
        run_remote=_run_remote,
        start_tunnel=_start_tunnel,
    )
    return {
        "schema_version": 1,
        "kind": "comfy-tunnel-ensure",
        "ok": bool(rep.get("ok")),
        "action": rep.get("action"),
        "local_port": config.local_port,
        "remote_port": config.remote_port,
        "target": config.target,
        "remote_service_restarted": rep.get("remote_service_restarted"),
        "notes": notes,
        "recovery": rep,
    }
